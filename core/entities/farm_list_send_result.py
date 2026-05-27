"""
Entidad FarmListSendResult — resultado inmediato del envío de una farm list.

Devuelto por FarmListBrowserPort.send_farm_list() tras pulsar el botón Start
y leer el estado del DOM (farmListStatus).

`status`: success | partial | error | unknown (RN-12)
  - success:  current >= active  (todos los slots activos enviaron)
  - partial:  0 < current < active
  - error:    current == 0 y active > 0 (sin tropas disponibles)
  - unknown:  active == 0 (todas las vacas desactivadas, EC-10)

`being_raided_current`: slots actualmente raideando (X en "X/Y being raided").
`being_raided_total`:   slots activos en la lista en el momento del envío.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FarmListSendResult:
    farm_list_id: int
    status: str          # success | partial | error | unknown
    being_raided_current: int = 0
    being_raided_total: int = 0
