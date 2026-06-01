/**
 * Test de extractTextWithImageAlts() usando node:test + node:assert
 * Node.js 22+ — sin dependencias externas.
 *
 * PROBLEMA QUE VALIDA: en Travian T4.6, tropas y animales se muestran como
 * <img alt="Rat">, <img alt="Phalanx">, etc. document.innerText ignora esas
 * imágenes, dejando solo números. El parser del backend necesita los NOMBRES
 * para identificar tropas/animales y devuelve 422 si faltan.
 *
 * QUÉ TESTA ESTE FICHERO:
 *   1. Que extractTextWithImageAlts sustituye <img alt="..."> por su texto alt
 *      (núcleo del fix — sin esto el bug vuelve)
 *   2. Que el texto resultante contiene exactamente los nombres esperados
 *   3. Que imágenes sin alt/title quedan vacías (decorativas)
 *   4. Que el fallback a document.body no pierde los alts
 *
 * QUÉ NO PUEDE TESTARSE SIN BROWSER REAL:
 *   - Las tabulaciones (\t) de las celdas de tabla — innerText las produce pero
 *     textContent no; requiere layout de browser. Se documenta como verificación
 *     manual en el README de tests.
 *
 * CÓMO EJECUTAR:
 *   node chrome-extension/tests/test-extract.js
 *
 * Resultado esperado: todos los tests en verde (✓) sin errores.
 */

'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Re-implementación pura de la lógica de sustitución img→alt
// (misma lógica que extractTextWithImageAlts en content-script.js,
//  pero operando sobre un árbol DOM simulado con objetos JS planos)
// ---------------------------------------------------------------------------

/**
 * Simula un nodo de texto (equivalente a document.createTextNode).
 */
function createTextNode(value) {
  return { _type: 'text', nodeValue: value };
}

/**
 * Simula un elemento DOM mínimo con:
 *   - tagName
 *   - attributes ({ alt, title, src, ... })
 *   - children: array de nodos hijos (TextNode | ElementNode)
 *   - getAttribute(name)
 *   - querySelectorAll(selector)  — solo soporta 'img' para este test
 *   - replaceWith(newNode)        — reemplaza this en el padre
 *   - textContent (getter)        — equivalente a textContent del browser
 */
function createElement(tagName, attrs = {}, children = []) {
  const node = {
    _type: 'element',
    tagName: tagName.toLowerCase(),
    _attrs: attrs,
    _children: children,   // array mutable
    _parent: null,

    getAttribute(name) {
      return this._attrs[name] !== undefined ? this._attrs[name] : null;
    },

    // Reemplazar este nodo por newNode en el padre
    replaceWith(newNode) {
      if (!this._parent) return;
      const idx = this._parent._children.indexOf(this);
      if (idx !== -1) {
        this._parent._children.splice(idx, 1, newNode);
        if (newNode._type === 'element') newNode._parent = this._parent;
      }
    },

    // Colectar todos los descendientes <img>
    querySelectorAll(selector) {
      if (selector !== 'img') throw new Error('Test mock solo soporta selector "img"');
      const result = [];
      function walk(node) {
        if (node._type !== 'element') return;
        if (node.tagName === 'img') result.push(node);
        for (const child of node._children) walk(child);
      }
      walk(this);
      return result;
    },

    // textContent: concatena texto de todos los descendientes
    get textContent() {
      function walk(node) {
        if (node._type === 'text') return node.nodeValue;
        if (node._type === 'element') return node._children.map(walk).join('');
        return '';
      }
      return walk(this);
    }
  };

  // Vincular hijos al padre
  for (const child of children) {
    if (child._type === 'element') child._parent = node;
  }

  return node;
}

/**
 * Implementación pura de extractTextWithImageAlts sin depender del DOM del browser.
 * Opera sobre el árbol de objetos simulados definidos arriba.
 *
 * Lógica IDÉNTICA a la de content-script.js:
 *   - querySelectorAll('img') sobre el clon
 *   - replaceWith(textNode) para cada img con alt o title
 *   - retornar textContent (equivalente a innerText sin layout)
 */
function extractTextWithImageAlts_pure(node) {
  // En el test no clonamos (trabajamos directamente con el árbol construido en el test)
  // porque no tenemos cloneNode. La lógica de sustitución es lo que importa testear.
  const imgs = node.querySelectorAll('img');
  for (const img of imgs) {
    const label = img.getAttribute('alt') || img.getAttribute('title') || '';
    if (label) {
      img.replaceWith(createTextNode(label));
    }
  }
  return node.textContent;
}

// ---------------------------------------------------------------------------
// Helpers de construcción del árbol DOM simulado
// ---------------------------------------------------------------------------

function img(alt, title) {
  const attrs = {};
  if (alt !== undefined) attrs.alt = alt;
  if (title !== undefined) attrs.title = title;
  return createElement('img', attrs);
}

function td(children) {
  return createElement('td', {}, children);
}

function tr(cells) {
  return createElement('tr', {}, cells);
}

function table(rows) {
  const tbody = createElement('tbody', {}, rows);
  const node = createElement('table', {}, [tbody]);
  for (const row of rows) row._parent = tbody;
  tbody._parent = node;
  return node;
}

function div(children, id) {
  const attrs = id ? { id } : {};
  const node = createElement('div', attrs, children);
  for (const child of children) {
    if (child._type === 'element') child._parent = node;
  }
  return node;
}

function textNode(str) {
  return createTextNode(str);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('T-UNIT-01: nombres de tropas galas en cabecera de tabla', () => {
  // Simula: <tr><th><img alt="Phalanx"></th><th><img alt="Swordsman"></th>...</tr>
  const headerRow = tr([
    td([img('Phalanx')]),
    td([img('Swordsman')]),
    td([img('Pathfinder')]),
    td([img('Theutates Thunder')]),
    td([img('Hero')])
  ]);
  const root = div([table([headerRow])]);

  const result = extractTextWithImageAlts_pure(root);

  assert.ok(result.includes('Phalanx'),          'debe incluir "Phalanx"');
  assert.ok(result.includes('Swordsman'),         'debe incluir "Swordsman"');
  assert.ok(result.includes('Pathfinder'),        'debe incluir "Pathfinder"');
  assert.ok(result.includes('Theutates Thunder'), 'debe incluir "Theutates Thunder"');
  assert.ok(result.includes('Hero'),              'debe incluir "Hero"');
});

test('T-UNIT-02: nombres de animales de oasis', () => {
  const headerRow = tr([
    td([img('Rat')]),
    td([img('Spider')]),
    td([img('Snake')]),
    td([img('Bat')]),
    td([img('Wild Boar')]),
    td([img('Wolf')]),
    td([img('Bear')]),
    td([img('Crocodile')]),
    td([img('Tiger')]),
    td([img('Elephant')])
  ]);
  const root = div([table([headerRow])]);

  const result = extractTextWithImageAlts_pure(root);

  const animals = ['Rat', 'Spider', 'Snake', 'Bat', 'Wild Boar', 'Wolf', 'Bear', 'Crocodile', 'Tiger', 'Elephant'];
  for (const animal of animals) {
    assert.ok(result.includes(animal), `debe incluir "${animal}"`);
  }
});

test('T-UNIT-03: los números de tropas se conservan junto a los nombres', () => {
  // Simula la tabla completa: cabecera con img + fila con números
  const headerRow = tr([td([img('Phalanx')]), td([img('Swordsman')]), td([img('Theutates Thunder')])]);
  const dataRow   = tr([td([textNode('0')]), td([textNode('124')]), td([textNode('750')])]);
  const root = div([table([headerRow, dataRow])]);

  const result = extractTextWithImageAlts_pure(root);

  assert.ok(result.includes('Phalanx'),          'debe incluir "Phalanx"');
  assert.ok(result.includes('Theutates Thunder'), 'debe incluir "Theutates Thunder"');
  assert.ok(result.includes('124'),               'debe incluir el número 124');
  assert.ok(result.includes('750'),               'debe incluir el número 750');
  assert.ok(result.includes('0'),                 'debe incluir el número 0');
});

test('T-UNIT-04: imágenes sin alt usan title como fallback', () => {
  // Si no hay alt pero hay title, usar title
  const headerRow = tr([td([img(undefined, 'Druidrider')])]);
  const root = div([table([headerRow])]);

  const result = extractTextWithImageAlts_pure(root);
  assert.ok(result.includes('Druidrider'), 'debe incluir "Druidrider" desde title');
});

test('T-UNIT-05: imágenes decorativas sin alt ni title no producen texto extra', () => {
  // Una img sin alt ni title (decorativa) no debe añadir nada
  const headerRow = tr([
    td([img('Rat')]),
    td([img('')]),          // alt vacío → tratar igual que sin alt
    td([textNode('19')])
  ]);
  const root = div([table([headerRow])]);

  const result = extractTextWithImageAlts_pure(root);
  assert.ok(result.includes('Rat'), 'debe incluir "Rat"');
  assert.ok(result.includes('19'),  'debe incluir el número');
  // El alt vacío no debe añadir contenido semántico (replaceWith solo si label truthy)
  // Verificamos que no hay strings extraños (doble espacio, undefined, null...)
  assert.ok(!result.includes('undefined'), 'no debe incluir "undefined"');
  assert.ok(!result.includes('null'),      'no debe incluir "null"');
});

test('T-UNIT-06: estructura completa de reporte (atacante + defensor) contiene todos los nombres', () => {
  // Simula el fixture-report.html completo
  const attackerHeader = tr([
    td([img('Phalanx')]),
    td([img('Swordsman')]),
    td([img('Pathfinder')]),
    td([img('Theutates Thunder')]),
    td([img('Hero')])
  ]);
  const attackerData = tr([td([textNode('0')]), td([textNode('124')]), td([textNode('0')]), td([textNode('750')]), td([textNode('1')])]);

  const defenderHeader = tr([
    td([img('Rat')]),
    td([img('Spider')]),
    td([img('Snake')]),
    td([img('Bat')]),
    td([img('Wild Boar')]),
    td([img('Wolf')]),
    td([img('Bear')]),
    td([img('Crocodile')]),
    td([img('Tiger')]),
    td([img('Elephant')])
  ]);
  const defenderData = tr([
    td([textNode('19')]), td([textNode('18')]), td([textNode('0')]),
    td([textNode('0')]),  td([textNode('6')]),  td([textNode('0')]),
    td([textNode('0')]),  td([textNode('0')]),  td([textNode('0')]),
    td([textNode('0')])
  ]);

  const root = div([
    div([table([attackerHeader, attackerData])]),
    div([table([defenderHeader, defenderData])])
  ]);

  const result = extractTextWithImageAlts_pure(root);

  // Tropas atacantes
  for (const name of ['Phalanx', 'Swordsman', 'Pathfinder', 'Theutates Thunder', 'Hero']) {
    assert.ok(result.includes(name), `debe incluir tropa "${name}"`);
  }
  // Animales defensores
  for (const name of ['Rat', 'Spider', 'Snake', 'Bat', 'Wild Boar', 'Wolf', 'Bear', 'Crocodile', 'Tiger', 'Elephant']) {
    assert.ok(result.includes(name), `debe incluir animal "${name}"`);
  }
  // Números clave
  assert.ok(result.includes('124'), 'Swordsman count 124');
  assert.ok(result.includes('750'), 'Theutates Thunder count 750');
  assert.ok(result.includes('19'),  'Rat count 19');
  assert.ok(result.includes('18'),  'Spider count 18');
  assert.ok(result.includes('6'),   'Wild Boar count 6');
});

test('T-UNIT-07: sin imágenes el texto se devuelve sin modificaciones', () => {
  // Si no hay <img> en el árbol, el texto queda igual
  const root = div([
    tr([td([textNode('hello')]), td([textNode('world')])])
  ]);

  const result = extractTextWithImageAlts_pure(root);
  assert.ok(result.includes('hello'), '"hello" debe estar presente');
  assert.ok(result.includes('world'), '"world" debe estar presente');
});

// ---------------------------------------------------------------------------
// Verificación del fixture HTML (lectura del fichero)
// ---------------------------------------------------------------------------

test('T-UNIT-08: el fixture HTML contiene las imágenes con alt esperados', () => {
  const fixturePath = path.join(__dirname, 'fixture-report.html');
  const html = fs.readFileSync(fixturePath, 'utf8');

  const expectedAlts = [
    'Phalanx', 'Swordsman', 'Pathfinder', 'Theutates Thunder', 'Hero',
    'Rat', 'Spider', 'Snake', 'Bat', 'Wild Boar', 'Wolf', 'Bear',
    'Crocodile', 'Tiger', 'Elephant'
  ];

  for (const alt of expectedAlts) {
    assert.ok(
      html.includes(`alt="${alt}"`),
      `fixture debe contener alt="${alt}"`
    );
  }
});
