# Cómo contribuir

El proyecto es un único archivo HTML sin dependencias ni paso de compilación. Para trabajar:
cloná el repo y abrí `index.html` en el navegador. No hace falta nada más.

## Qué tipo de aporte es más útil

**Correcciones con fuente.** Si un número o una fórmula no coincide con tu bibliografía o con
datos de banco, abrí un *issue* indicando la fuente. Las correcciones documentadas se aceptan.

**Propelentes nuevos.** Los presets están en el objeto `PRESETS` dentro de `index.html`. Para
agregar uno hace falta: γ, masa molar, temperatura de llama, densidad, y los coeficientes `a` y `n`
de la ley de quemado con sus unidades. **Incluí siempre la referencia** en el campo `src` y en
`ATRIBUCIONES.md`, y marcá explícitamente si los valores son aproximados.

**Modelo.** Capa límite, erosión de garganta, flujo bifásico y transitorio de ignición están fuera
del alcance actual. Si querés abordar alguno, planteá primero el enfoque en un *issue*.

## Criterios del código

- Sin dependencias y sin paso de compilación. Si una propuesta obliga a meter una librería o un
  bundler, hablémoslo antes.
- Toda constante física lleva unidad explícita en un comentario, y el cálculo interno va en SI.
- Un dato que viene de una fuente lleva la cita junto al dato, no solo en el README.
- La app debe seguir funcionando abierta como archivo local, sin servidor y sin conexión.
- Los textos de la interfaz están en español rioplatense.

## Antes de abrir un pull request

Comprobá a mano que:

1. El caso por defecto sigue dando ≈673 N con `c*` ≈ 1580 m/s y ε ≈ 6,98.
2. Los menús de descarga de las cinco secciones siguen funcionando.
3. Guardar, cargar, exportar e importar configuraciones sigue funcionando.
4. La app no desborda horizontalmente a 400 px de ancho.
5. El conmutador de tema repinta el dibujo correctamente.

Si tocaste la física, contrastala también contra `cli/laval-studio-cli.py`: las dos
implementaciones tienen que dar el mismo resultado.
