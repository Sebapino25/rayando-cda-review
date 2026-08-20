// Sparklines de mediakit/, sin librería externa (mismo criterio "sin build
// tool" que el resto del sitio): arma un SVG a mano a partir de puntos
// {t: Date, v: number}. Lo usan tanto public/app.js (2 gráficos resumidos)
// como dashboard/app.js (los 9 completos).

function construirSparkline(svg, puntos, opts = {}) {
  const color = opts.color || '#2E6BE0'
  const relleno = opts.relleno || 'rgba(46,107,224,0.14)'
  const datos = puntos.filter((p) => p.t instanceof Date && !isNaN(p.t) && typeof p.v === 'number' && Number.isFinite(p.v))
  if (datos.length < 2) return null

  const w = 600
  const h = 160
  const padX = 14
  const padY = 18
  const tMin = datos[0].t.getTime()
  const tMax = datos[datos.length - 1].t.getTime()
  const vMin = Math.min(...datos.map((p) => p.v))
  const vMax = Math.max(...datos.map((p) => p.v))
  // Si todos los puntos valen lo mismo (o hay un solo timestamp real), evita
  // dividir por 0: la línea queda plana en el medio en vez de romper el SVG.
  const rangoT = Math.max(tMax - tMin, 1)
  const rangoV = Math.max(vMax - vMin, 1)

  const x = (t) => padX + ((t.getTime() - tMin) / rangoT) * (w - padX * 2)
  const y = (v) => h - padY - ((v - vMin) / rangoV) * (h - padY * 2)

  const linea = datos.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.t).toFixed(1)} ${y(p.v).toFixed(1)}`).join(' ')
  const area = `${linea} L ${x(datos[datos.length - 1].t).toFixed(1)} ${(h - padY).toFixed(1)} L ${x(datos[0].t).toFixed(1)} ${(h - padY).toFixed(1)} Z`
  const puntosSvg = datos
    .map((p) => `<circle cx="${x(p.t).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="4" fill="${color}"></circle>`)
    .join('')

  svg.setAttribute('viewBox', `0 0 ${w} ${h}`)
  svg.setAttribute('preserveAspectRatio', 'none')
  svg.innerHTML = `<path d="${area}" fill="${relleno}" stroke="none"></path><path d="${linea}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>${puntosSvg}`

  const primero = datos[0]
  const ultimo = datos[datos.length - 1]
  return {
    primero,
    ultimo,
    crecimientoPct: primero.v > 0 ? Math.round(((ultimo.v - primero.v) / primero.v) * 100) : null,
  }
}
