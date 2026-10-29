# Atribuciones y origen de los datos

Este documento registra de dónde viene cada parte, separando lo publicado de lo aproximado.

## Código de terceros

Ninguno. La app no carga librerías: todo el cálculo y el dibujo SVG están escritos para este
proyecto. Lo único externo son las tipografías IBM Plex, servidas por Google Fonts bajo
[SIL Open Font License 1.1](https://openfontlicense.org/), con respaldo del sistema si no cargan.

## Tabla de ángulos de Rao (campana TOP)

Los arrays `RAO_TN` y `RAO_TE` —ángulo inicial y de salida de la parábola en función de la
relación de expansión y del porcentaje de longitud— están digitalizados del gráfico clásico de
G. V. R. Rao y fueron tomados de:

> **ravi4ram/Bell-Nozzle** — https://github.com/ravi4ram/Bell-Nozzle
> Copyright (c) 2020 ravi4ram — Licencia MIT

La licencia MIT de ese repositorio es compatible con la de este proyecto; el requisito es
conservar su aviso de copyright, que es el propósito de esta sección.

**Nota técnica.** La fila del 60 % de longitud presenta una no-monotonía en ε = 50 (37,1 → 35,0 →
40,0) que parece un artefacto de digitalización de esa fuente. Está marcada en un comentario del
código. La fila del 80 % es la recomendada y es el valor estándar de diseño.

## Construcción geométrica de la campana

Arco de entrada de 1,5·R_t entre −135° y −90°, arco de salida de 0,382·R_t entre −90° y
(θn − 90°), y Bézier cuadrática con el punto de control en la intersección de las tangentes.
Longitud de referencia `L_n = 0,8·(√ε − 1)·R_t / tan 15°` para la campana al 80 %.

> **AspireSpace** — *The Thrust Optimised Parabolic nozzle*
> https://www.aspirespace.org.uk/downloads/Thrust%20optimised%20parabolic%20nozzle.pdf

Es una técnica publicada; se cita por trazabilidad, no por obligación de licencia.

## Propiedades del propelente

### APCP AP/HTPB aluminizado — publicado

> Godil, J. & Kamran, A. (2017). *Numerical simulation of ignition transient in solid rocket
> motor: a revisit*. Aircraft Engineering and Aerospace Technology 89(6), 936–945, Tabla I.
> https://doi.org/10.1108/AEAT-04-2015-0109

γ = 1,20 · M = 27,71 g/mol · T_c = 3500 K · ρ = 1760 kg/m³ · a = 1,559 mm/s·bar^−0,47 · n = 0,47

### KNSU candy KNO₃/sacarosa 65/35 — aproximado, sin verificar

Valores del orden de los publicados por Richard Nakka (*Experimental Rocketry Web Site*):
T_c = 1720 K · M = 41,98 g/mol · γ = 1,133 · ρ = 1889 kg/m³ · r = 8,26·P^0,319 (mm/s, MPa).

**No están contrastados contra la fuente primaria.** Se incluyen como punto de partida razonable.
Comprobación indirecta: la `c*` que calcula la app con esas propiedades da 919 m/s, coherente con
los ~885 m/s publicados una vez descontada la eficiencia — eso valida la fórmula, no los datos de
entrada. Caracterizá tu lote antes de usarlos.

## Formulación

Las relaciones de flujo isentrópico, la función de Vandenkerckhove, `c*`, el coeficiente de empuje,
la ley de Saint-Robert y el equilibrio de `Kn` son material estándar de la disciplina. La referencia
canónica es:

> Sutton, G. P. & Biblarz, O. *Rocket Propulsion Elements*. Wiley.

Lo mismo vale para los criterios de aviso: el criterio de Summerfield para desprendimiento de la
capa límite y los rangos habituales de semiángulo (12–18° divergente, 30–45° convergente).

## Referencias de contexto

Usadas para acotar rangos de presión y márgenes de dimensionado, sin aportar fórmulas al código:

- Lacruz, L. et al. (2016). *Análisis experimental de las oscilaciones de presión interna en un
  motor de combustible sólido para cohete sonda*. Revista Ciencia e Ingeniería 37(2), 81–88.
  — órdenes de magnitud de presión de cámara con propelente candy.
- d'Agostino, L., Biagioni, L. & Lamberti, G. (2001). *An Ignition Transient Model for Solid
  Propellant Rocket Motors*. AIAA 2001-3449. — incertidumbre de escalado de ±6 %.
