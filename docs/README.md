# Documentación de WowHub

Bienvenido a la documentación del proyecto. Aquí encontrarás los informes,
changelogs y material de referencia para el equipo de desarrollo, producto
y para los clientes.

---

## 📑 Índice de documentos

### Para clientes
- 📄 **[Informe del Módulo de Reservas (Bookings)](INFORME_BOOKINGS.md)** —
  Sistema de agendamiento online con detección de conflictos, validación de horarios, UI de agenda, landing público y exposición al asistente IA.
- 📄 **[Informe de Integración del Asistente Virtual](INFORME_INTEGRACION_IA.md)** —
  Resumen ejecutivo de la integración IA ↔ módulos de negocio, beneficios y roadmap.
- 📄 **[Informe del Sistema de Fidelización (Loyalty Pass)](INFORME_FIDELIZACION.md)** —
  Tarjetas digitales con sellos, QR rotativo anti-fraude, modos de aplicación y roadmap.

### Para el equipo
- 📋 **[Changelog](../docs/CHANGELOG.md)** — Historial de cambios del proyecto.
- 🏗️ **[README principal](../README.md)** — Setup, instalación y arquitectura general.

---

## 🗂️ Cómo está organizada la documentación

```
docs/
├── README.md                       ← este archivo (índice)
├── CHANGELOG.md                    ← historial de cambios
├── INFORME_INTEGRACION_IA.md       ← informe de la fase de integración IA
├── INFORME_FIDELIZACION.md         ← informe del sistema de fidelización
└── INFORME_BOOKINGS.md             ← informe del módulo de reservas (Fase 2)
```

---

## 🔄 Cómo mantener esta carpeta actualizada

1. **Cuando agregues una nueva funcionalidad importante**, crea un `INFORME_<TEMA>.md`
   con el mismo formato que `INFORME_INTEGRACION_IA.md` (resumen ejecutivo + técnico).
2. **Cuando hagas commits**, añade una entrada en `CHANGELOG.md` bajo `[No publicado]`
   con la fecha actual y la categoría (`Added`, `Changed`, `Fixed`, etc.).
3. **Cuando subas la documentación al repo**, commitea y pushea con un mensaje
   claro, por ejemplo:
   ```
   docs: añadir informe de integración IA + changelog
   ```

---

## 📌 Convenciones de los informes

Cada informe para cliente debe incluir:

1. **Resumen ejecutivo** — qué se hizo, en lenguaje no técnico.
2. **Beneficios de negocio** — qué gana el cliente con esto.
3. **Detalles técnicos** — endpoints, servicios, modelos, métricas.
4. **Pruebas y calidad** — cobertura y resultados.
5. **Roadmap** — próximos pasos sugeridos.

---

*Mantenedor: equipo WowHub · Última actualización: 2026-08-16*
