/**
 * Índice del catálogo i18n.
 * Carga eager todos los idiomas. Para un app grande convendría
 * lazy-load por idioma, pero con 25 ficheros pequeños el bundle
 * es manejable.
 *
 * Fallback: si una clave no existe en el idioma activo, se usa
 * el catálogo 'es' (base completo).
 */
import es from './es.js'
import en from './en.js'
import de from './de.js'
import fr from './fr.js'
import it from './it.js'
import pt from './pt.js'
import ru from './ru.js'
import ar from './ar.js'
import he from './he.js'
import fa from './fa.js'
import ja from './ja.js'
import bg from './bg.js'
import cs from './cs.js'
import da from './da.js'
import el from './el.js'
import hu from './hu.js'
import lt from './lt.js'
import lv from './lv.js'
import nl from './nl.js'
import pl from './pl.js'
import rs from './rs.js'
import sl from './sl.js'
import sv from './sv.js'
import tr from './tr.js'
import uk from './uk.js'

const CATALOG = {
  ar, bg, cs, da, de, el, en, es,
  fa, fr, he, hu, it, ja, lt, lv,
  nl, pl, pt, rs, ru, sl, sv, tr, uk,
}

export default CATALOG
