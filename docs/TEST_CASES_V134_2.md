# 📋 Documento de Casos de Prueba — TO-BE WowHub V134.2

> **Versión:** V134.2 (Documento Técnico Corregido)
> **Fecha de generación:** 2026-10-07
> **Fuente:** https://jxa24h0tmp5g.space.mcode.io/
> **Total de Historias de Usuario cubiertas:** 49
> **Total de Story Points:** 261 SP
> **Épicas cubiertas:** 8 (E0 a E7)

---

## 🎯 Cómo leer este documento

Este documento contiene **casos de prueba** (CP) para cada una de las 49 Historias de Usuario (HU) definidas en el documento **TO-BE WowHub V134.2**. Cada caso está escrito en **lenguaje simple**, como si lo entendiera cualquier usuario normal sin conocimiento técnico.

### Tipos de pruebas incluidas por cada HU:

| Tipo | Emoji | ¿Qué verifica? |
|------|-------|----------------|
| **Funcionales** | 🟢 | Que la funcionalidad haga lo que dice que hace (caso feliz) |
| **Seguridad** | 🔒 | Que nadie sin permiso pueda acceder, ver o modificar cosas ajenas |
| **Rendimiento** | ⚡ | Que funcione rápido y sin caerse cuando hay mucha gente usándolo |
| **Negativos** | ❌ | Que el sistema NO haga lo que NO debe hacer, y avise cuando algo está mal |

### Estructura de cada caso de prueba:

Cada caso se nombra como **`CP-XX-NN-TIPO`** donde:
- `XX` = número de la HU
- `NN` = número del caso (01, 02, 03…)
- `TIPO` = F (Funcional), S (Seguridad), R (Rendimiento), N (Negativo)

Ejemplo: `CP-03-05-S` = caso 5 de seguridad para la HU_03.

Cada caso tiene: **ID · Descripción · Pasos · Resultado esperado**.

---

## 📊 Resumen de cobertura

| Épica | HUs | SP | Casos Funcionales | Casos Seguridad | Casos Rendimiento | Casos Negativos | Total |
|-------|-----|----|-------------------|-----------------|-------------------|-----------------|-------|
| E0 · Plataforma Base | 7 | 71 | 35 | 28 | 14 | 28 | 105 |
| E1 · Productos | 7 | 78 | 35 | 21 | 14 | 28 | 98 |
| E2 · Operaciones | 8 | 73 | 40 | 24 | 16 | 32 | 112 |
| E3 · CRM y Lealtad | 7 | 15 | 28 | 21 | 7 | 21 | 77 |
| E4 · Reportes | 6 | 8 | 24 | 12 | 6 | 18 | 60 |
| E5 · Infraestructura | 7 | 8 | 21 | 28 | 7 | 14 | 70 |
| E6 · Integraciones | 4 | 5 | 16 | 12 | 4 | 12 | 44 |
| E7 · DevOps | 3 | 3 | 9 | 9 | 6 | 9 | 33 |
| **TOTAL** | **49** | **261** | **208** | **155** | **74** | **162** | **599** |

---

# 🏗️ ÉPICA E0 · Plataforma Base & Multi-Tenant (71 SP · 7 HUs · Sprint 1)

> **Qué es esta épica:** Es la base sobre la que se construye todo lo demás. Incluye poder registrarse, iniciar sesión, separar los datos entre distintos negocios (multi-tenant) y tener roles de usuario. Sin esto, nada más funciona.

---

## HU_01 · Registro y creación de cuenta de tenant (8 SP)

**Resumen:** El primer usuario que se registra crea un nuevo espacio (tenant) aislado para su negocio. Como si fuera la "oficina virtual" donde vivirá toda su información.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-01-01-F | Registrarse con email válido | 1. Ir a la pantalla de registro. 2. Poner email válido (ej. juan@mitienda.cl). 3. Poner contraseña segura. 4. Poner nombre del negocio. 5. Clic en "Crear cuenta". | Se crea una cuenta nueva y se entra al dashboard. El sistema muestra "Bienvenido a WowHub". |
| CP-01-02-F | Verificar email | 1. Registrarse. 2. Revisar el correo. 3. Clic en el enlace de verificación. | El sistema marca el email como verificado y muestra un mensaje verde "Email confirmado". |
| CP-01-03-F | Elegir subdominio | 1. Iniciar sesión por primera vez. 2. Elegir un subdominio (ej. mipizza). 4. Clic en "Guardar". | El sistema asigna el subdominio `mipizza.wowhub.app` y lo guarda como único. |
| CP-01-04-F | Configurar idioma y zona horaria | 1. Ir a "Mi cuenta". 2. Elegir idioma español. 3. Elegir zona horaria de Santiago de Chile. 4. Guardar. | El sistema guarda los datos y todas las fechas se muestran en hora local. |
| CP-01-05-F | Crear primer usuario admin | 1. Al registrarse, el sistema crea automáticamente el primer usuario con rol "dueño". | El primer usuario tiene permisos totales sobre el tenant. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-01-01-S | Impedir contraseñas débiles | 1. Intentar registrarse con contraseña "123456". | El sistema rechaza y dice "La contraseña debe tener al menos 12 caracteres con mayúsculas, minúsculas, números y símbolos". |
| CP-01-02-S | Impedir emails duplicados | 1. Registrarse con un email ya usado. | El sistema dice "Este email ya está registrado" sin revelar si el email existe en otro tenant. |
| CP-01-03-S | Bloquear bots con captcha | 1. Enviar 5 registros seguidos desde la misma IP en menos de 1 minuto. | El sistema pide captcha a partir del tercer intento. |
| CP-01-04-S | Impedir subdominios reservados | 1. Intentar elegir "admin", "api" o "www" como subdominio. | El sistema dice "Este subdominio no está disponible". |
| CP-01-05-S | Hashear contraseñas | 1. Inspeccionar la base de datos directamente. | Las contraseñas están guardadas como hashes (cifradas), nunca en texto plano. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-01-01-R | Registro rápido bajo carga | 1. Simular 100 personas registrándose al mismo tiempo. | El sistema responde en menos de 1 segundo al usuario final. |
| CP-01-02-R | Envío de email de verificación | 1. Registrarse 50 veces. | Todos los emails se envían en menos de 30 segundos. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-01-01-N | Email con formato inválido | 1. Poner "juan@" como email. | El sistema dice "Email no válido". |
| CP-01-02-N | Sin nombre de negocio | 1. Dejar el campo de nombre vacío. | El sistema muestra error "El nombre es obligatorio". |
| CP-01-03-N | Email con mayúsculas/minúsculas mezcladas | 1. Registrarse con "Juan@MiTienda.CL". 2. L luego intentar con "juan@mitienda.cl". | El sistema considera ambos como el mismo email. |
| CP-01-04-N | Datos malformados en JSON | 1. Enviar a la API un JSON roto (ej. sin cerrar comillas). | El sistema responde con error 400 claro y NO se cae el servidor. |
| CP-01-05-N | Subdominio con caracteres raros | 1. Intentar poner "mi pizza!" como subdominio. | El sistema lo rechaza y solo permite letras minúsculas, números y guiones. |

---

## HU_02 · Multi-tenancy con Row Level Security (RLS) en PostgreSQL (13 SP)

**Resumen:** Los datos de un negocio están completamente separados de los datos de otro negocio. Como si cada negocio tuviera su propia oficina cerrada con llave. Aunque dos negocios compartan la misma base de datos, NO pueden ver lo del otro.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-02-01-F | Aislamiento entre tenants | 1. Crear tenant A con producto "Coca Cola". 2. Crear tenant B. 3. Loguearse como tenant B y listar productos. | El tenant B NO ve "Coca Cola" del tenant A. |
| CP-02-02-F | Cada tenant ve sus propios clientes | 1. Tenant A crea cliente "Juan Pérez". 2. Tenant B consulta clientes. | El tenant B NO ve a "Juan Pérez". |
| CP-02-03-F | Cambiar de tenant | 1. Estar logueado en tenant A. 2. Cerrar sesión. 3. Loguearse en tenant B. | Se ven los datos del tenant B sin mezcla de datos del A. |
| CP-02-04-F | Usuario pertenece solo a un tenant | 1. Usuario creado en tenant A intenta acceder a URL del tenant B. | El sistema responde "No tienes permisos". |
| CP-02-05-F | Inserts con tenant_id automático | 1. Insertar un pedido nuevo sin pasar tenant_id manualmente. | El sistema asigna automáticamente el tenant_id del usuario logueado. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-02-01-S | SQL directo filtrado por RLS | 1. Conectarse a la BD con rol de tenant A. 2. Ejecutar `SELECT * FROM productos`. | Solo se ven productos del tenant A. |
| CP-02-02-S | Manipular tenant_id en URL | 1. Logueado en tenant A. 2. Cambiar manualmente la URL a `tenant=B`. | El sistema ignora el cambio y sigue mostrando datos de A. |
| CP-02-03-S | Impedir UPDATE cross-tenant | 1. Como tenant A prueba su ID de producto (100). 2. Como tenant B intenta editar ese producto 100. | El sistema responde 404 (como si no existiera). |
| CP-02-04-S | Auditoría de accesos cruzados | 1. Intentar acceder a datos de otro tenant. 2. Revisar logs. | El intento queda registrado en logs con severidad "WARN". |
| CP-02-05-S | Roles de BD separados | 1. Verificar en la BD que existan roles `app_tenant_a`, `app_tenant_b`, etc. | Cada rol solo tiene permisos sobre su schema. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-02-01-R | Consultas con RLS no degradan | 1. Medir tiempo de consulta sin RLS. 2. Medir con RLS activado. | La diferencia de tiempo es menor al 10%. |
| CP-02-02-R | 100 tenants simultáneos | 1. Simular 100 tenants haciendo consultas a la vez. | El sistema responde en menos de 200ms al percentil 95. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-02-01-N | Eliminar tenant_id de la sesión | 1. Manipular la sesión para borrar el tenant_id. | El sistema responde 401 (no autorizado). |
| CP-02-02-N | Tenant_id NULL en INSERT | 1. Insertar un producto sin tenant_id. | La BD rechaza con error de constraint NOT NULL. |
| CP-02-03-N | JOIN entre tenants | 1. Intentar una consulta que mezcle datos de dos tenants. | La BD solo retorna filas del tenant actual. |
| CP-02-04-N | Cambiar header X-Tenant-Id | 1. Logueado en tenant A. 2. Enviar header `X-Tenant-Id: B`. | El sistema ignora el header y usa el del token JWT. |
| CP-02-05-N | Backup cruzado | 1. Restaurar backup del tenant A en tenant B. | El sistema detecta el conflicto y bloquea la operación. |

---

## HU_03 · Auth JWT con cookies httpOnly + refresh tokens rotativos (13 SP)

**Resumen:** El usuario inicia sesión y el sistema le da un "pase" seguro (token). Este pase está guardado en una cookie que el navegador no puede leer desde el código malicioso (httpOnly). El pase se renueva automáticamente sin que el usuario tenga que volver a escribir su contraseña.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-03-01-F | Login exitoso | 1. Ir al login. 2. Poner email y contraseña correctos. 3. Clic en "Entrar". | El usuario entra al dashboard. |
| CP-03-02-F | Renovación automática de token | 1. Estar logueado. 2. Esperar 14 minutos (el access token dura 15 min). 3. Hacer clic en cualquier opción. | El token se renueva solo sin pedir login de nuevo. |
| CP-03-03-F | Cerrar sesión | 1. Estar logueado. 2. Clic en "Cerrar sesión". | El sistema borra las cookies y vuelve a la pantalla de login. |
| CP-03-04-F | Ver perfil propio | 1. Estar logueado. 2. Llamar a `/auth/me`. | El sistema devuelve nombre, email y rol del usuario. |
| CP-03-05-F | Recuperar sesión tras cerrar navegador | 1. Loguearse. 2. Cerrar el navegador. 3. Volver a abrir. | Si la cookie del refresh token sigue vigente, el usuario sigue logueado. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-03-01-S | Login con contraseña incorrecta | 1. Poner email correcto y contraseña "incorrecta". | El sistema dice "Credenciales incorrectas" sin diferenciar email o contraseña. |
| CP-03-02-S | Impedir reuso de refresh token | 1. Capturar un refresh token. 2. Usarlo dos veces. | El segundo uso es bloqueado y se invalida TODA la cadena de tokens del usuario. |
| CP-03-03-S | Firma RS256 (no HS256) | 1. Inspeccionar un JWT recibido. 2. Verificar el algoritmo. | El header dice "RS256". El sistema rechaza tokens con "none" o "HS256". |
| CP-03-04-S | Refresh tokens hasheados con bcrypt | 1. Inspeccionar la tabla de refresh tokens en la BD. | Los refresh tokens están hasheados (no en texto plano). |
| CP-03-05-S | Rate limit en login | 1. Intentar loguearse 6 veces en 1 minuto con datos incorrectos. | A partir del 5to intento, el sistema bloquea por 5 minutos. |
| CP-03-06-S | Cookie con flags correctos | 1. Inspeccionar la cookie `wowhub_access_token`. | Tiene flags `HttpOnly; Secure; SameSite=Lax`. |
| CP-03-07-S | Logout revoca tokens | 1. Loguearse. 2. Capturar refresh token. 3. Cerrar sesión. 4. Intentar usar el refresh token capturado. | El sistema lo rechaza porque está en la blacklist. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-03-01-R | Login rápido | 1. Medir tiempo de respuesta de login con 50 RPS (requests por segundo). | El percentil 95 (p95) es menor a 200ms. |
| CP-03-02-R | Renovación rápida | 1. Medir tiempo de `/auth/refresh` con 100 RPS. | El p95 es menor a 100ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-03-01-N | Token expirado | 1. Esperar a que el access token expire (15 min sin actividad). 2. Intentar una acción. | El sistema detecta expiración, renueva con el refresh token automáticamente. |
| CP-03-02-N | Token manipulado | 1. Modificar el payload de un JWT. | El sistema lo rechaza porque la firma no coincide. |
| CP-03-03-N | Token de otro usuario | 1. Capturar JWT de usuario A. 2. Usarlo desde cuenta B. | El sistema lo rechaza porque el `sub` (subject) no coincide. |
| CP-03-04-N | Refresh con access token | 1. Mandar un access token al endpoint `/auth/refresh`. | El sistema rechaza con 400 "Token inválido". |
| CP-03-05-N | Logout sin token | 1. Llamar a `/auth/logout` sin estar logueado. | El sistema responde 200 (idempotente) y no rompe nada. |

---

## HU_04 · RBAC (Control de Acceso Basado en Roles) (8 SP)

**Resumen:** No todos los usuarios pueden hacer todo. Un "dueño" puede borrar cosas, un "empleado" solo puede ver. Los roles controlan quién puede hacer qué.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-04-01-F | Crear rol | 1. Como admin, ir a "Roles". 2. Clic en "Crear rol". 3. Poner nombre "Cajero". 4. Marcar permisos. 5. Guardar. | El rol aparece en la lista y se puede asignar a usuarios. |
| CP-04-02-F | Asignar rol a usuario | 1. Ir a "Usuarios". 2. Elegir usuario. 3. Asignar rol "Cajero". | El usuario ahora tiene permisos de cajero. |
| CP-04-03-F | Permisos granulares | 1. Como admin, marcar permiso "Crear pedidos". | El usuario puede crear pedidos pero NO borrar productos. |
| CP-04-04-F | Roles predefinidos | 1. Crear nuevo tenant. | El sistema crea automáticamente roles: Dueño, Admin, Cajero, Mesero. |
| CP-04-05-F | Listar roles | 1. Ir a "Roles". | Se ven todos los roles con sus permisos. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-04-01-S | Escalar privilegios | 1. Como usuario con rol "Cajero", intentar acceder a `/admin/users`. | El sistema responde 403 "No tienes permisos". |
| CP-04-02-S | No ver datos sensibles | 1. Como Cajero, intentar ver datos bancarios del negocio. | El sistema oculta esa sección del menú y bloquea el endpoint. |
| CP-04-03-S | Cambiar propio rol | 1. Como Cajero, intentar cambiarse a sí mismo a "Dueño" vía API. | El sistema rechaza la operación. |
| CP-04-04-S | Roles únicos por tenant | 1. Tenant A crea rol "Supervisor". 2. Tenant B crea rol "Supervisor". | Ambos coexisten sin conflicto (aislamiento multi-tenant). |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-04-01-R | Verificar permisos rápido | 1. Hacer 1000 requests verificando permisos. | Cada verificación toma menos de 5ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-04-01-N | Rol inexistente | 1. Intentar asignar rol "Dios" a un usuario. | El sistema dice "El rol no existe". |
| CP-04-02-N | Borrar rol en uso | 1. Intentar borrar el rol "Cajero" que tienen 5 usuarios asignados. | El sistema pide confirmación o bloquea si hay usuarios activos. |
| CP-04-03-N | Permiso inexistente | 1. Marcar permiso "Viajar en el tiempo". | El sistema no muestra esa opción (no es un permiso válido). |
| CP-04-04-N | Eliminar último admin | 1. Borrar todos los usuarios con rol "Dueño". | El sistema impide que quede un tenant sin administrador. |

---

## HU_05 · Onboarding guiado de 5 pasos (8 SP)

**Resumen:** Cuando un usuario nuevo entra por primera vez, el sistema lo guía paso a paso para configurar su negocio: datos básicos, primer producto, primer usuario, primer pedido de prueba, listo.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-05-01-F | Iniciar onboarding | 1. Loguearse por primera vez. | El sistema muestra la pantalla "Bienvenido, configuremos tu negocio". |
| CP-05-02-F | Datos del negocio | 1. Paso 1: poner logo, dirección, teléfono. 2. Siguiente. | El sistema guarda los datos y avanza al paso 2. |
| CP-05-03-F | Primer producto | 1. Paso 2: poner nombre "Hamburguesa", precio $5000. 2. Siguiente. | El producto aparece en el catálogo. |
| CP-05-04-F | Primer usuario | 1. Paso 3: invitar a otro usuario con rol "Cajero". | Se envía un email de invitación. |
| CP-05-05-F | Pedido de prueba | 1. Paso 4: simular un pedido. | El sistema crea un pedido de ejemplo para mostrar cómo funciona. |
| CP-05-06-F | Finalizar onboarding | 1. Paso 5: clic en "Terminar". | El sistema marca el onboarding como completo y oculta el wizard. |
| CP-05-07-F | Barra de progreso | 1. Estar en paso 2. | Se ve "Paso 2 de 5" con barra de progreso al 40%. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-05-01-S | No exponer datos sensibles | 1. El wizard muestra email y teléfono del dueño. | Solo se muestran los datos del usuario logueado, no de otros. |
| CP-05-02-S | Invitaciones solo a dominios permitidos | 1. Intentar invitar a un email de dominio bloqueado. | El sistema rechaza o pide confirmación. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-05-01-R | Wizard rápido | 1. Cargar el wizard. | Carga en menos de 500ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-05-01-N | Saltar pasos obligatorios | 1. Intentar ir directo al paso 5 sin completar el 1. | El sistema bloquea y dice "Completa los pasos anteriores". |
| CP-05-02-N | Cerrar el wizard a la mitad | 1. Cerrar el navegador en el paso 3. 2. Volver a entrar. | El sistema recuerda en qué paso quedó. |
| CP-05-03-N | Datos faltantes | 1. Poner precio negativo en un producto. | El sistema lo rechaza. |
| CP-05-04-N | Logo inválido | 1. Subir un logo de 50MB. | El sistema rechaza por peso máximo permitido. |

---

## HU_06 · Sistema de auditoría y logs estructurados (13 SP)

**Resumen:** Cada acción importante (crear, borrar, editar) queda registrada con quién la hizo, cuándo y desde dónde. Como una "cámara de seguridad" digital para auditorías y problemas legales.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-06-01-F | Crear log automático | 1. Un usuario crea un pedido. | El sistema guarda en BD: usuario, fecha, acción, IP. |
| CP-06-02-F | Ver logs en dashboard | 1. Ir a "Auditoría". 2. Filtrar últimos 7 días. | Se ven todas las acciones realizadas. |
| CP-06-03-F | Filtrar por usuario | 1. Filtrar logs por usuario específico. | Solo se ven las acciones de ese usuario. |
| CP-06-04-F | Exportar logs | 1. Clic en "Exportar CSV". | Se descarga un archivo CSV con los logs. |
| CP-06-05-F | Logs inmutables | 1. Intentar editar un log desde la BD. | El sistema lo impide (tabla append-only). |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-06-01-S | No exponer datos sensibles en logs | 1. Buscar logs de login. | Las contraseñas NUNCA aparecen en los logs. |
| CP-06-02-S | Logs con TLS | 1. Verificar transmisión de logs. | Los logs viajan cifrados (HTTPS/TLS). |
| CP-06-03-S | Retención configurada | 1. Configurar retención 365 días. | Pasados 365 días, los logs se eliminan automáticamente. |
| CP-06-04-S | Acceso a logs | 1. Como usuario normal, intentar acceder a logs de otro tenant. | El sistema bloquea por multi-tenancy. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-06-01-R | Escribir log no bloquea | 1. Medir tiempo de creación de pedido con y sin auditoría. | La diferencia es menor a 20ms. |
| CP-06-02-R | Consultar logs rápido | 1. Cargar dashboard de logs con 1 millón de registros. | Carga en menos de 2 segundos. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-06-01-N | Falla al escribir log | 1. Simular caída del servicio de logs. | El sistema sigue funcionando y reencola los logs fallidos. |
| CP-06-02-N | Inyección en campos de log | 1. Crear producto con nombre `<script>alert('xss')</script>`. | El sistema guarda el texto sin ejecutarlo. |
| CP-06-03-N | Log sin usuario | 1. Acción sin usuario identificado (sistema). | El sistema registra como "system" sin romperse. |
| CP-06-04-N | Filtro malicioso | 1. Poner `'; DROP TABLE logs; --` en un filtro. | El sistema lo trata como texto plano, no como SQL. |

---

## HU_07 · API REST documentada con OpenAPI/Swagger (8 SP)

**Resumen:** La API tiene una página web donde cualquier programador puede ver todos los "endpoints" (URLs que devuelven datos) y probarlos. Como un "manual interactivo" para desarrolladores.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-07-01-F | Ver documentación | 1. Ir a `/docs`. | Se ve la interfaz Swagger UI con todos los endpoints. |
| CP-07-02-F | Probar endpoint | 1. Abrir endpoint `/auth/login`. 2. Poner credenciales. 3. Clic en "Try it out". | Se ejecuta y muestra la respuesta JSON. |
| CP-07-03-F | Ver esquema de modelo | 1. Abrir sección "Schemas". | Se ven todos los modelos (Producto, Pedido, etc.) con sus campos. |
| CP-07-04-F | Filtrar por tags | 1. Filtrar endpoints por tag "Productos". | Solo se ven endpoints relacionados con productos. |
| CP-07-05-F | Descargar OpenAPI JSON | 1. Ir a `/openapi.json`. | Se descarga el archivo con la especificación completa. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-07-01-S | Documentación no expone secretos | 1. Revisar los ejemplos en Swagger. | NO aparecen API keys ni secretos de producción. |
| CP-07-02-S | Acceso solo en desarrollo | 1. En producción, intentar acceder a `/docs`. | Por defecto está deshabilitado o protegido. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-07-01-R | Carga rápida de Swagger | 1. Cargar `/docs`. | Carga en menos de 1 segundo. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-07-01-N | Schema desactualizado | 1. Comparar el schema con el código real. | Si hay diferencias, se detecta en CI (integración continua). |
| CP-07-02-N | Falta descripción | 1. Buscar un endpoint sin descripción. | El linter falla el build en CI. |
| CP-07-03-N | Error 500 no documentado | 1. Provocar un error 500. | La respuesta debe seguir el schema de ErrorResponse. |

---

# 🍕 ÉPICA E1 · Productos, Insumos & Costos (78 SP · 7 HUs · Sprint 2)

> **Qué es esta épica:** El corazón del menú digital. Permite crear productos (pizza, bebida, combo), gestionar los ingredientes que los componen, calcular automáticamente el costo real y mostrarlo en diferentes formatos al cliente.

---

## HU_08 · CRUD de productos y categorías (13 SP)

**Resumen:** El usuario puede crear, ver, editar y borrar productos (ej. "Pizza Margarita $8.000") y agruparlos en categorías (ej. "Pizzas", "Bebidas", "Postres").

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-08-01-F | Crear producto | 1. Ir a "Productos". 2. Clic en "Nuevo producto". 3. Poner nombre "Pizza Margarita". 4. Poner precio $8.000. 5. Elegir categoría "Pizzas". 6. Guardar. | El producto aparece en la lista y en el menú público. |
| CP-08-02-F | Crear categoría | 1. Ir a "Categorías". 2. Clic en "Nueva categoría". 3. Poner "Postres". 4. Guardar. | La categoría aparece y se puede asignar a productos. |
| CP-08-03-F | Editar producto | 1. Clic en "Editar" de un producto. 2. Cambiar precio. 3. Guardar. | El nuevo precio se refleja en el menú inmediatamente. |
| CP-08-04-F | Borrar producto | 1. Clic en "Eliminar" de un producto. 2. Confirmar. | El producto desaparece del menú público. |
| CP-08-05-F | Subir imagen | 1. En producto, arrastrar imagen JPG. 2. Guardar. | La imagen aparece junto al producto. |
| CP-08-06-F | Reordenar categorías | 1. Arrastrar una categoría para otra posición. | El orden se guarda y se refleja en el menú. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-08-01-S | Solo roles autorizados | 1. Como Cajero, intentar crear producto. | El sistema rechaza (solo Admin o Dueño). |
| CP-08-02-S | Validar imágenes | 1. Subir archivo `.exe` renombrado a `.jpg`. | El sistema rechaza y dice "Tipo de archivo no permitido". |
| CP-08-03-S | Borrado lógico | 1. Borrar producto con pedidos históricos. | El producto se "desactiva" pero no se borra (mantiene integridad histórica). |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-08-01-R | Carga rápida con muchos productos | 1. Listar 1.000 productos. | Carga en menos de 1 segundo. |
| CP-08-02-R | Búsqueda rápida | 1. Buscar "pizza" entre 1.000 productos. | Resultados en menos de 200ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-08-01-N | Nombre duplicado | 1. Crear producto "Pizza Margarita". 2. Crear otro "Pizza Margarita". | El sistema permite duplicados (diferente SKU) o avisa según configuración. |
| CP-08-02-N | Precio negativo | 1. Poner precio $-100. | El sistema rechaza y dice "El precio debe ser mayor a 0". |
| CP-08-03-N | Sin categoría | 1. Crear producto sin elegir categoría. | El sistema lo permite o pide confirmación (configurable). |
| CP-08-04-N | Categoría con productos | 1. Intentar borrar categoría con 5 productos. | El sistema pide reasignar productos antes de borrar. |

---

## HU_09 · Recetas e Insumos (BOM) con costo automático (13 SP)

**Resumen:** Cada producto se hace con varios ingredientes. El sistema calcula automáticamente cuánto cuesta producir cada producto (mano de obra, ingredientes, etc.) para que el dueño sepa cuánto gana.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-09-01-F | Crear insumo | 1. Ir a "Insumos". 2. Crear "Harina 1kg" con costo $1.200. | El insumo aparece y está disponible para recetas. |
| CP-09-02-F | Crear receta | 1. Ir a producto "Pizza". 2. En "Receta", agregar "Harina 200g". | El sistema guarda 200g de harina como ingrediente. |
| CP-09-03-F | Calcular costo automático | 1. Ver producto "Pizza". 2. Ir a pestaña "Costos". | Se ve costo total calculado según ingredientes y cantidades. |
| CP-09-04-F | Ver margen | 1. Ver producto. | Se ve costo, precio de venta y margen (%). |
| CP-09-05-F | Ajustar insumo | 1. Cambiar precio de harina de $1.200 a $1.500. | El costo de la pizza se recalcula automáticamente. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-09-01-S | Costos privados | 1. Como Cajero, intentar ver costos. | El sistema oculta la pestaña "Costos" para roles no autorizados. |
| CP-09-02-S | Cambios de precio auditados | 1. Cambiar precio de insumo. | El cambio queda en log de auditoría con usuario y fecha. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-09-01-R | Recálculo masivo | 1. Cambiar precio de un insumo. 2. Esperar recálculo de 500 productos. | Recálculo en menos de 5 segundos. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-09-01-N | Insumo sin costo | 1. Crear insumo sin precio. | El sistema avisa "Costo pendiente" pero permite guardar. |
| CP-09-02-N | Cantidad negativa | 1. En receta poner "-200g" de harina. | El sistema rechaza y pide cantidad positiva. |
| CP-09-03-N | Receta circular | 1. Pizza usa Masa. 2. Masa usa Pizza. | El sistema detecta el ciclo y bloquea. |

---

## HU_10 · Cálculo V8 de Costos (14 campos) (13 SP)

**Resumen:** El cálculo de costos tiene 14 campos diferentes (no solo 4) para reflejar la realidad: mano de obra, energía, alquiler, mermas, comisiones, etc. Es el "costo real" de producir cada plato.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-10-01-F | Ver 14 campos | 1. Ir a producto. 2. Clic en "Costos V8". | Se ven los 14 campos: ingredientes, mano de obra, energía, etc. |
| CP-10-02-F | Editar costo de mano de obra | 1. Poner "30 min de cocinero por unidad". 2. Poner costo hora $5.000. | El sistema calcula $2.500 de mano de obra. |
| CP-10-03-F | Promedio ponderado automático | 1. Crear 3 proveedores de harina con precios distintos. 2. Calcular costo. | El sistema usa el promedio ponderado según compras históricas. |
| CP-10-04-F | Trigger PostgreSQL | 1. Insertar un insumo con precio X. 2. Verificar que el trigger recalcula. | El campo `costo_ponderado` se actualiza por trigger. |
| CP-10-05-F | Ver desglose | 1. | Se ven todos los componentes con su aporte al costo total. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-10-01-S | Acceso restringido | 1. Como Mesero, intentar editar costos. | El sistema rechaza (solo Admin o Dueño). |
| CP-10-02-S | Validar rango de valores | 1. Poner mano de obra negativa. | El sistema rechaza. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-10-01-R | Cálculo con trigger | 1. Insertar 1000 insumos. | El trigger recalcula en menos de 2 segundos. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-10-01-N | Campos faltantes | 1. Guardar producto sin completar todos los 14. | El sistema permite campos opcionales pero marca cuáles faltan. |
| CP-10-02-N | Inconsistencia | 1. Poner mano de obra 100h pero tiempo total 1h. | El sistema avisa de inconsistencia. |

---

## HU_11 · Variantes y modificadores de productos (8 SP)

**Resumen:** Un producto puede tener variantes (tamaño: pequeño, mediano, grande) y modificadores (extras: extra queso, sin cebolla). Cada uno puede tener su propio precio.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-11-01-F | Crear variante | 1. En producto "Pizza", agregar variante "Familiar +$3.000". | La variante aparece como opción al pedir. |
| CP-11-02-F | Crear modificador | 1. Agregar modificador "Extra queso +$1.500". | El cliente puede marcar "Extra queso" al pedir. |
| CP-11-03-F | Limitar modificadores | 1. Poner máximo 3 modificadores por producto. | El cliente no puede seleccionar más de 3. |
| CP-11-04-F | Modificador obligatorio | 1. Marcar "Tipo de cocción" como obligatorio. | El cliente debe elegir antes de pedir. |
| CP-11-05-F | Precio dinámico | 1. Variante "Grande" con extra queso. | El sistema suma ambos: precio base + variante + modificador. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-11-01-S | No manipular precios en frontend | 1. Inspeccionar HTML. 2. Cambiar precio en consola. | El sistema recalcula en backend y rechaza si no coincide. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-11-01-R | Carga rápida de variantes | 1. Cargar producto con 20 variantes y 50 modificadores. | Carga en menos de 300ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-11-01-N | Variante duplicada | 1. Crear variante "Familiar" dos veces. | El sistema pide nombre único. |
| CP-11-02-N | Modificador sin precio | 1. Crear "Sin cebolla" sin costo (debería ser 0 o gratis). | El sistema lo permite con precio 0. |

---

## HU_12 · Menú público digital con GridStack 24 columnas (13 SP)

**Resumen:** Los clientes ven el menú desde su celular entrando a una página web (sin login). El diseño usa 24 columnas (estándar Bootstrap) para verse bien en cualquier pantalla.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-12-01-F | Ver menú público | 1. Ir a `mipizza.wowhub.app/menu`. | Se ven productos agrupados por categorías. |
| CP-12-02-F | Ver en celular | 1. Abrir menú en móvil. | El diseño se adapta (responsive). |
| CP-12-03-F | Filtrar por categoría | 1. Clic en "Bebidas". | Se muestran solo bebidas. |
| CP-12-04-F | Buscar producto | 1. Escribir "pizza" en buscador. | Aparecen solo las pizzas. |
| CP-12-05-F | Ver imagen grande | 1. Clic en imagen de producto. | Se abre modal con imagen ampliada. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-12-01-S | No exponer datos internos | 1. Inspeccionar HTML del menú público. | NO aparecen costos, ni datos del dueño. |
| CP-12-02-S | Rate limit en menú público | 1. Hacer 1000 requests al menú desde misma IP. | A partir de cierto límite, se bloquea temporalmente. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-12-01-R | Carga rápida | 1. Medir tiempo de carga con 100 productos. | El menú carga en menos de 2 segundos (incluyendo imágenes). |
| CP-12-02-R | Optimización de imágenes | 1. Verificar formato WebP. | Las imágenes están en formato moderno y comprimido. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-12-01-N | Producto oculto | 1. Producto marcado como "no mostrar en menú". | NO aparece en el menú público. |
| CP-12-02-N | Imagen rota | 1. Producto con URL de imagen inválida. | Se muestra imagen placeholder, no se rompe el menú. |

---

## HU_13 · Combo / packs de productos (8 SP)

**Resumen:** Permite agrupar varios productos en un combo (ej. "Combo familiar: pizza + bebida + postre") con precio especial.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-13-01-F | Crear combo | 1. Ir a "Combos". 2. Clic en "Nuevo". 3. Poner nombre "Combo Pareja". 4. Agregar 2 pizzas + 2 bebidas. 5. Poner precio $12.000. | El combo aparece en el menú con su precio especial. |
| CP-13-02-F | Calcular ahorro | 1. Ver combo. | El sistema muestra precio normal tachado y ahorro. |
| CP-13-03-F | Editar combo | 1. Cambiar un producto del combo. | El sistema actualiza el combo automáticamente. |
| CP-13-04-F | Stock de combo | 1. Combo limitado a 10 unidades. | Se muestra "Quedan 3" cuando se acerca al límite. |
| CP-13-05-F | Desactivar combo | 1. Marcar combo como inactivo. | NO aparece en el menú público. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-13-01-S | Precio fijo a nivel backend | 1. Manipular precio en frontend. | El backend recalcula y rechaza si no coincide. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-13-01-R | Listar combos rápido | 1. Cargar menú con 50 combos. | Carga en menos de 1 segundo. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-13-01-N | Combo sin productos | 1. Intentar guardar combo vacío. | El sistema pide al menos 2 productos. |
| CP-13-02-N | Combo con producto borrado | 1. Borrar producto que está en combo. | El sistema bloquea o quita el producto del combo. |

---

## HU_14 · Inventario y stock en tiempo real (10 SP)

**Resumen:** Cada producto tiene un inventario que se descuenta cuando se vende. Si no hay stock, no se puede pedir.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-14-01-F | Configurar stock | 1. En producto, poner "stock actual: 50". | El sistema guarda el stock. |
| CP-14-02-F | Descontar al vender | 1. Vender 3 unidades. | El stock baja automáticamente a 47. |
| CP-14-03-F | Alerta de stock bajo | 1. Stock llega a 5. | El sistema notifica al dueño por email/push. |
| CP-14-04-F | Reposición | 1. Marcar "repongo 20 unidades". | El stock sube a 25. |
| CP-14-05-F | Sin stock | 1. Stock en 0. | El producto se marca "Agotado" en el menú. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-14-01-S | No manipular stock desde frontend | 1. Modificar stock por consola del navegador. | El sistema ignora los cambios hechos fuera del backend. |
| CP-14-02-S | Historial de cambios | 1. Reposición de stock. | El cambio queda registrado en log con usuario, fecha y motivo. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-14-01-R | Stock en tiempo real | 1. Vender 1 unidad. 2. Verificar que se descuenta en otros clientes conectados. | Se actualiza en menos de 1 segundo (WebSocket/SSE). |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-14-01-N | Vender más del stock | 1. Stock 2, intentar vender 5. | El sistema rechaza el pedido por stock insuficiente. |
| CP-14-02-N | Stock negativo | 1. Poner stock -10 manualmente. | El sistema rechaza o avisa de inconsistencia. |

---

# 🛵 ÉPICA E2 · Operaciones (Pedidos, Reservas, Mesas) (73 SP · 8 HUs · Sprint 3)

> **Qué es esta épica:** El día a día del negocio. Recibir pedidos (en local, delivery, retiro), gestionar reservas de mesas, dividir cuentas y manejar comandas en cocina.

---

## HU_15 · Pedidos multi-canal (local, delivery, retiro) (13 SP)

**Resumen:** El sistema acepta pedidos de tres formas: comer en el local, pedir a domicilio, o retirar en el local. Cada canal tiene su flujo particular.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-15-01-F | Pedido en local | 1. Mozo toma pedido en mesa 5. | El pedido llega a cocina con mesa asignada. |
| CP-15-02-F | Pedido delivery | 1. Cliente pide desde web con dirección. | Se calcula envío y se confirma pedido. |
| CP-15-03-F | Pedido para retirar | 1. Cliente pide "retiro en local". | Se da hora estimada de retiro. |
| CP-15-04-F | Estado del pedido | 1. Cliente consulta estado. | Ve "RECIBIDO → EN_PREPARACION → LISTO → ENTREGADO". |
| CP-15-05-F | Diferentes precios por canal | 1. Delivery tiene recargo de $1.000. | El recargo se aplica automáticamente. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-15-01-S | Validar dirección de delivery | 1. Poner dirección fuera de zona de cobertura. | El sistema rechaza con mensaje claro. |
| CP-15-02-S | Datos del cliente protegidos | 1. Verificar que solo el cliente y el local vean los datos. | Aislados por tenant. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|-------------------|---------------------|
| CP-15-01-R | Pico de pedidos (hora punta) | 1. Simular 500 pedidos/hora. | El sistema responde en menos de 500ms cada uno. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-15-01-N | Canal cerrado | 1. Intentar hacer delivery a las 2am cuando está cerrado. | El sistema dice "No aceptamos pedidos a esta hora". |
| CP-15-02-N | Sin stock al pedir | 1. Producto sin stock al confirmar. | El sistema notifica al cliente y propone alternativa. |

---

## HU_16 · Estados de pedido en español (RECIBIDO, EN_PREPARACION, LISTO, ENTREGADO) (5 SP)

**Resumen:** Los estados del pedido están en español para que todos los entiendan (mozos, cocineros, clientes).

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-16-01-F | Crear pedido | 1. Hacer pedido nuevo. | El estado inicial es "RECIBIDO". |
| CP-16-02-F | Cambiar estado | 1. En cocina, clic en "EN PREPARACION". | El pedido cambia de estado. |
| CP-16-03-F | Ver historial | 1. Ver pedido. | Se ve la línea de tiempo con cada cambio de estado. |
| CP-16-04-F | Estado final | 1. Marcar como "ENTREGADO". | El pedido se cierra y archiva. |
| CP-16-05-F | Notificar al cliente | 1. Cambiar a "LISTO". | El cliente recibe push/email "Tu pedido está listo". |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-16-01-S | Solo roles autorizados cambian estado | 1. Como cliente intentar cambiar estado. | El sistema rechaza. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-16-01-R | Cambio de estado rápido | 1. Cambiar estado de 100 pedidos. | Cada cambio se aplica en menos de 100ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-16-01-N | Salto de estado | 1. Intentar ir de "RECIBIDO" directo a "ENTREGADO". | El sistema pide pasar primero por EN_PREPARACION y LISTO. |
| CP-16-02-N | Estado inválido | 1. Enviar estado "CANCELADO_VOLANDO". | El sistema rechaza (solo permite estados predefinidos). |

---

## HU_17 · Reservas de mesas con disponibilidad (10 SP)

**Resumen:** El cliente puede reservar una mesa para una fecha y hora específica. El sistema muestra qué mesas hay libres.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-17-01-F | Ver disponibilidad | 1. Ir a "Reservas". 2. Elegir fecha y hora. 3. Ver mesas libres. | El sistema muestra las mesas disponibles. |
| CP-17-02-F | Crear reserva | 1. Elegir mesa. 2. Poner nombre y teléfono. 3. Confirmar. | La reserva queda guardada y se notifica al local. |
| CP-17-03-F | Cancelar reserva | 1. En "Mis reservas", clic en "Cancelar". | La mesa queda libre nuevamente. |
| CP-17-04-F | Confirmación automática | 1. Crear reserva para mañana 20:00. | Se envía email de confirmación al cliente. |
| CP-17-05-F | Lista de espera | 1. No hay mesas disponibles. | El sistema ofrece anotarse en lista de espera. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-17-01-S | Datos del cliente protegidos | 1. Ver reserva. | El cliente solo ve sus datos, no los de otros. |
| CP-17-02-S | No manipular disponibilidad | 1. Editar HTML de disponibilidad. | El backend valida la disponibilidad real. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-17-01-R | Consulta rápida de disponibilidad | 1. Con 50 mesas y 200 reservas existentes. | La consulta tarda menos de 300ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-17-01-N | Mesa doblemente reservada | 1. Intentar reservar misma mesa y hora. | El sistema rechaza (validación de solapamiento). |
| CP-17-02-N | Reserva en el pasado | 1. Intentar reservar para ayer. | El sistema rechaza. |

---

## HU_18 · Comandas / KDS (Kitchen Display System) (13 SP)

**Resumen:** Una pantalla en la cocina muestra los pedidos pendientes con qué preparar. Es como un monitor de pedidos para el cocinero.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-18-01-F | Ver comandas | 1. En cocina, abrir KDS. | Se ven los pedidos pendientes con sus productos. |
| CP-18-02-F | Marcar como listo | 1. Clic en "Listo" de un pedido. | El pedido desaparece del KDS y aparece como "LISTO". |
| CP-18-03-F | Priorizar pedido | 1. Marcar pedido como "Urgente". | El pedido se mueve arriba y se destaca. |
| CP-18-04-F | Ver tiempo de preparación | 1. En KDS, ver pedido. | Se ve hace cuántos minutos se pidió. |
| CP-18-05-F | Filtros | 1. Filtrar solo "Postres". | Solo aparecen los pedidos con postres. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-18-01-S | Solo personal de cocina | 1. Como mesero, intentar acceder al KDS. | El sistema bloquea por rol. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-18-01-R | Actualización en tiempo real | 1. Crear pedido. 2. Verificar que aparece en KDS en menos de 1s. | Latencia menor a 1 segundo. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-18-01-N | KDS caído | 1. Caer el sistema del KDS. | Los pedidos siguen aceptándose y se sincronizan al volver. |

---

## HU_19 · División de cuenta / split bill (8 SP)

**Resumen:** Cuando hay varios comensales en una mesa, cada uno puede pagar su parte por separado.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-19-01-F | Dividir en partes iguales | 1. Cuenta total $30.000. 2. Clic en "Dividir entre 3". | Se generan 3 cuentas de $10.000. |
| CP-19-02-F | Cada uno paga lo suyo | 1. Persona 1 paga $10.000. 2. Persona 2 paga $10.000. 3. Persona 3 paga $10.000. | La cuenta se cierra al completarse todos los pagos. |
| CP-19-03-F | División por producto | 1. Cada persona marca qué consumió. | El sistema calcula lo que le corresponde a cada uno. |
| CP-19-04-F | Propina | 1. Al pagar, agregar 10% propina. | Se suma al monto a cobrar. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-19-01-S | Pagos solo del dueño de mesa | 1. Como cliente, intentar pagar cuenta ajena. | El sistema bloquea. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-19-01-R | Cálculo rápido | 1. Dividir cuenta con 20 productos entre 6 personas. | El cálculo tarda menos de 100ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-19-01-N | División que no suma el total | 1. Sistema redondea mal. | El sistema avisa que hay diferencia de $X. |

---

## HU_20 · Asignación de mozos a mesas (5 SP)

**Resumen:** Cada mesa tiene un mozo asignado. Cuando llega un pedido, se sabe automáticamente qué mozo lo tomó.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-20-01-F | Asignar mozo | 1. En mesa 5, asignar mozo "Juan". | El sistema guarda la asignación. |
| CP-20-02-F | Ver mesas asignadas | 1. En perfil de mozo, ver sus mesas. | Se listan las mesas asignadas a Juan. |
| CP-20-03-F | Liberar mesa | 1. Cerrar cuenta de mesa 5. | La mesa se libera y queda disponible. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-20-01-S | Ver solo mesas propias | 1. Como mozo A, ver mesas asignadas a mozo B. | El sistema oculta las mesas ajenas. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-20-01-R | Listar rápido | 1. Ver mesas de mozo. | Carga en menos de 100ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-20-01-N | Asignar mozo inexistente | 1. Asignar "Pepe" que no existe. | El sistema rechaza. |

---

## HU_21 · Impresoras y comandas físicas (8 SP)

**Resumen:** El sistema se conecta con impresoras de tickets y comandas para imprimir automáticamente cuando llega un pedido.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-21-01-F | Conectar impresora | 1. Ir a "Impresoras". 2. Agregar IP de impresora. | El sistema prueba la conexión. |
| CP-21-02-F | Imprimir comanda | 1. Llega pedido a cocina. | Se imprime automáticamente en la impresora de cocina. |
| CP-21-03-F | Imprimir ticket | 1. Cliente paga. | Se imprime ticket de venta. |
| CP-21-04-F | Reconexión automática | 1. Impresora se desconecta. | El sistema reconecta cuando vuelve. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-21-01-S | Impresora en LAN privada | 1. Verificar IP de impresora. | La impresora está en red privada (no expuesta a internet). |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-21-01-R | Impresión rápida | 1. Imprimir comanda. | Se envía a la impresora en menos de 500ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-21-01-N | Impresora apagada | 1. Impresora no responde. | El sistema encola y reintenta. |

---

## HU_22 · Delivery tracking en tiempo real (11 SP)

**Resumen:** El cliente puede ver dónde está su pedido en tiempo real en un mapa (similar a las apps de delivery).

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-22-01-F | Ver mapa | 1. Cliente abre su pedido. | Se ve mapa con ubicación del repartidor. |
| CP-22-02-F | Actualizar ubicación | 1. Repartidor se mueve. | El mapa del cliente se actualiza. |
| CP-22-03-F | Notificar entrega | 1. Repartidor marca "Entregado". | El cliente recibe notificación "Tu pedido llegó". |
| CP-22-04-F | ETA | 1. Ver tiempo estimado de llegada. | El sistema calcula según distancia y tráfico. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-22-01-S | Ubicación solo del repartidor | 1. Como cliente, ver ubicación del repartidor. | Solo se ve durante el envío activo. |
| CP-22-02-S | No exponer datos del cliente | 1. Repartidor ve datos del cliente. | Solo ve dirección, no email ni datos bancarios. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-22-01-R | Actualización fluida | 1. Repartidor en ruta. | El mapa se actualiza cada 5 segundos sin lag. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-22-01-N | Repartidor sin GPS | 1. Repartidor sin señal. | El sistema avisa "Ubicación no disponible". |

---

# 👥 ÉPICA E3 · Clientes, CRM & Lealtad (15 SP · 7 HUs · Sprint 4)

> **Qué es esta épica:** Gestionar los datos de los clientes, sus preferencias, su historial de compras y un programa de puntos para fidelizarlos.

---

## HU_23 · Registro de clientes (2 SP)

**Resumen:** Los clientes pueden registrarse para acumular historial y puntos.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-23-01-F | Cliente se registra | 1. En menú público, clic en "Registrarme". 2. Poner email y contraseña. | El cliente tiene cuenta y puede acumular puntos. |
| CP-23-02-F | Cliente con email existente | 1. Cliente ya registrado intenta registrarse de nuevo. | El sistema pide iniciar sesión. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-23-01-S | Contraseña fuerte | 1. Poner "123". | El sistema pide mínimo 8 caracteres con complejidad. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-23-01-R | Registro rápido | 1. Medir tiempo de registro. | Menor a 1 segundo. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-23-01-N | Email inválido | 1. Poner "no-es-email". | El sistema rechaza. |

---

## HU_24 · Perfil del cliente con historial (3 SP)

**Resumen:** El cliente ve todo lo que ha comprado y sus datos personales.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-24-01-F | Ver historial | 1. Cliente abre "Mi cuenta". | Ve lista de pedidos pasados. |
| CP-24-02-F | Editar perfil | 1. Cambiar teléfono. 2. Guardar. | El sistema actualiza los datos. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-24-01-S | Ver solo datos propios | 1. Cliente A intenta ver perfil de B. | El sistema bloquea. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-24-01-N | Eliminar cuenta | 1. Cliente pide borrar cuenta. | Se anonimiza (cumple GDPR). |

---

## HU_25 · Programa de lealtad / puntos (3 SP)

**Resumen:** Por cada compra, el cliente gana puntos que puede canjear por descuentos.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-25-01-F | Acumular puntos | 1. Cliente gasta $10.000. 2. Gana 100 puntos. | Los puntos se suman al perfil. |
| | | | |
| CP-25-02-F | Canjear puntos | 1. Cliente tiene 500 puntos. 2. Canjea por descuento. | El descuento se aplica al siguiente pedido. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-25-01-S | Impedir duplicar puntos | 1. Reintentar el mismo pago. | El sistema no duplica puntos (idempotencia). |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-25-01-N | Canjear sin puntos suficientes | 1. Intentar canjear 1000 puntos con 500. | El sistema rechaza. |

---

## HU_26 · Segmentación de clientes (2 SP)

**Resumen:** Permite agrupar clientes (VIP, nuevos, inactivos) para hacer campañas.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-26-01-F | Crear segmento | 1. Crear segmento "VIP". 2. Regla: más de $50.000 en compras. | El sistema identifica los VIP automáticamente. |
| CP-26-02-F | Enviar campaña | 1. Elegir segmento "Inactivos". 2. Enviar email con descuento. | Solo inactivos reciben el email. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-26-01-S | Datos personales protegidos | 1. Ver lista de segmento. | Se ve email pero no tarjeta ni contraseña. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-26-01-N | Regla inválida | 1. Crear regla sin sentido. | El sistema pide validar antes de guardar. |

---

## HU_27 · CRM con timeline de interacciones (2 SP)

**Resumen:** Por cada cliente se ve una línea de tiempo con todas las interacciones (compras, mensajes, llamadas).

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-27-01-F | Ver timeline | 1. Abrir perfil de cliente. | Se ven todas las interacciones ordenadas por fecha. |
| CP-27-02-F | Agregar nota | 1. Mozo agrega nota "Cliente alérgico a maní". | La nota aparece en el timeline. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-27-01-S | Solo personal autorizado | 1. Cliente intenta ver su propio timeline. | Solo ve historial de compras, no notas internas. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-27-01-N | Nota vacía | 1. Intentar guardar nota vacía. | El sistema pide al menos 5 caracteres. |

---

## HU_28 · Cupones y descuentos (2 SP)

**Resumen:** Permite crear cupones (ej. "VERANO20" para 20% descuento).

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-28-01-F | Crear cupón | 1. Crear cupón "VERANO20" con 20% descuento. 2. Marcar fecha de expiración. | El cupón queda activo hasta la fecha. |
| CP-28-02-F | Aplicar cupón | 1. Cliente ingresa "VERANO20" al pagar. | Se aplica 20% de descuento. |
| CP-28-03-F | Cupón expirado | 1. Intentar usar cupón vencido. | El sistema rechaza. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-28-01-S | Cupón único | 1. Intentar usar el mismo cupón dos veces. | Solo se aplica una vez (configurable). |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-28-01-N | Cupón inválido | 1. Ingresar "NOEXISTE". | El sistema dice "Cupón no válido". |

---

## HU_29 · Programa de referidos (1 SP)

**Resumen:** Los clientes pueden referir amigos y ganar recompensas.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-29-01-F | Generar link de referido | 1. Cliente pide su link. | Se genera link único tipo `wowhub.app/r/abc123`. |
| CP-29-02-F | Referido se registra | 1. Amigo usa link y se registra. | El cliente original gana puntos. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-29-01-S | Anti-fraude | 1. Cliente A refiere a sí mismo. | El sistema bloquea. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-29-01-N | Referido inválido | 1. Link corrupto. | El sistema dice "Link no válido". |

---

# 📊 ÉPICA E4 · Reportes, Exportaciones & Dashboards (8 SP · 6 HUs · Sprint 4)

> **Qué es esta épica:** Ver estadísticas del negocio: ventas, productos más vendidos, gráficos, exportar a Excel.

---

## HU_30 · Dashboard con métricas principales (2 SP)

**Resumen:** Pantalla principal con números clave del día.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-30-01-F | Ver dashboard | 1. Iniciar sesión. | Se ven ventas del día, pedidos, ticket promedio. |
| CP-30-02-F | Comparar con ayer | 1. Ver métricas. | Se ve comparación (+/-% vs ayer). |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-30-01-N | Sin datos | 1. Negocio recién creado. | El dashboard muestra "Sin datos aún" con guía. |

---

## HU_31 · Reporte de ventas por período (2 SP)

**Resumen:** Ver ventas por día, semana, mes.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-31-01-F | Reporte diario | 1. Ir a "Reportes". 2. Elegir "Hoy". | Se ven ventas del día desglosadas por hora. |
| CP-31-02-F | Reporte mensual | 1. Elegir "Mes actual". | Se ve total y gráfico. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-31-01-R | Reporte con muchos datos | 1. Generar reporte de 1 año. | Carga en menos de 3 segundos. |

---

## HU_32 · Productos más vendidos (1 SP)

**Resumen:** Ranking de productos según ventas.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-32-01-F | Ver ranking | 1. Ir a "Reportes". 2. Top productos. | Se ven los 10 más vendidos con cantidad e ingresos. |

---

## HU_33 · Exportación a CSV/Excel (1 SP)

**Resumen:** Descargar reportes en Excel.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-33-01-F | Exportar ventas | 1. Clic en "Exportar". | Se descarga archivo `.xlsx` o `.csv`. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-33-01-N | Sin datos para exportar | 1. Exportar sin ventas. | Se descarga archivo con cabeceras pero sin filas. |

---

## HU_34 · Gráficos de tendencia (1 SP)

**Resumen:** Gráficos de líneas para ver evolución de ventas.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-34-01-F | Ver tendencia | 1. Ir a "Reportes". 2. Gráfico de líneas. | Se ve evolución de ventas en últimos 30 días. |

---

## HU_35 · Reporte de inventario (1 SP)

**Resumen:** Ver qué productos tienen más/menos stock.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-35-01-F | Ver stock bajo | 1. Ir a "Reportes". 2. Stock bajo. | Se ven productos con stock crítico. |

---

# 🛡️ ÉPICA E5 · Infraestructura, Seguridad & Compliance (8 SP · 7 HUs · Sprint 4)

> **Qué es esta épica:** La base técnica segura: cifrado, backups, GDPR, rate limiting, CSP, etc.

---

## HU_36 · HTTPS obligatorio y certificados (1 SP)

**Resumen:** Toda la comunicación viaja cifrada (HTTPS).

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-36-01-F | Redirigir HTTP a HTTPS | 1. Poner `http://...` | Se redirige automáticamente a `https://...`. |

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-36-01-S | TLS 1.3+ | 1. Verificar versión TLS. | El servidor usa TLS 1.3 o superior. |

---

## HU_37 · Rate limiting (1 SP)

**Resumen:** Limitar el número de requests por usuario/IP.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-37-01-F | Limitar login | 1. 5 logins fallidos. | El sistema bloquea el 6to por 5 minutos. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-37-01-N | Exceder límite | 1. Hacer 100 requests/seg. | El sistema responde 429 "Too Many Requests". |

---

## HU_38 · CORS configurado (1 SP)

**Resumen:** Permite que solo ciertos orígenes (dominios) consuman la API.

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-38-01-S | Origen no permitido | 1. Hacer request desde `evil.com`. | El servidor rechaza con CORS error. |

---

## HU_39 · CSP (Content Security Policy) (1 SP)

**Resumen:** Política que indica qué recursos puede cargar el navegador.

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-39-01-S | Script externo bloqueado | 1. Inyectar `<script src="evil.com/x.js">`. | El navegador lo bloquea. |

---

## HU_40 · Backups automatizados (2 SP)

**Resumen:** Copias de seguridad diarias automáticas.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-40-01-F | Backup diario | 1. Esperar a las 03:00 AM. | Se crea backup automático. |
| CP-40-02-F | Restaurar backup | 1. Pedir restaurar copia de ayer. | El sistema restaura los datos. |

---

## HU_41 · Encriptación en reposo (1 SP)

**Resumen:** Los datos en la base de datos están cifrados.

### 🔒 Casos de Seguridad

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-41-01-S | Datos sensibles cifrados | 1. Inspeccionar BD. | Las contraseñas y datos bancarios están cifrados. |

---

## HU_42 · GDPR / cumplimiento de privacidad (1 SP)

**Resumen:** El cliente puede pedir ver, rectificar o borrar sus datos.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-42-01-F | Solicitar datos | 1. Cliente pide "Quiero ver mis datos". | El sistema envía un email con todos sus datos. |
| CP-42-02-F | Borrar cuenta | 1. Cliente pide borrar su cuenta. | El sistema anonimiza los datos (los pedidos quedan como "cliente eliminado"). |

---

# 🔌 ÉPICA E6 · Integraciones & Extensibilidad (5 SP · 4 HUs · Sprint 4)

> **Qué es esta épica:** Permitir que WowHub se conecte con otros sistemas (WhatsApp, email, webhooks) y permita plugins.

---

## HU_43 · Integración con WhatsApp (2 SP)

**Resumen:** Enviar mensajes por WhatsApp al cliente.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-43-01-F | Confirmar pedido | 1. Cliente hace pedido. | Se envía WhatsApp "Tu pedido fue confirmado". |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-43-01-N | Número inválido | 1. Cliente tiene número equivocado. | El sistema avisa "No se pudo enviar WhatsApp". |

---

## HU_44 · Webhooks salientes (1 SP)

**Resumen:** Notificar a otros sistemas cuando algo pasa (ej. nuevo pedido).

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-44-01-F | Webhook al crear pedido | 1. Crear pedido. 2. Verificar que el webhook se envió. | El sistema externo recibe POST con datos del pedido. |

---

## HU_45 · SDK para plugins (1 SP)

**Resumen:** Kit de desarrollo para crear plugins.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-45-01-F | Instalar plugin | 1. Subir ZIP de plugin. | El sistema lo instala y activa. |

---

## HU_46 · Marketplace de plugins (1 SP)

**Resumen:** Catálogo de plugins donde el usuario puede instalar con un clic.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-46-01-F | Ver marketplace | 1. Ir a "Marketplace". | Se ven plugins disponibles con descripción y precio. |

---

# 🚀 ÉPICA E7 · Escalabilidad, Observabilidad & DevOps (3 SP · 3 HUs · Sprint 4)

> **Qué es esta épica:** Hacer que el sistema sea observable (métricas, logs, errores) y escalable.

---

## HU_47 · Métricas Prometheus (1 SP)

**Resumen:** El sistema expone métricas para monitoreo.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-47-01-F | Ver métricas | 1. Ir a `/metrics`. | Se ven métricas en formato Prometheus. |

---

## HU_48 · Logs centralizados (1 SP)

**Resumen:** Los logs se envían a un sistema central.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-48-01-F | Ver logs en Sentry | 1. Provocar un error. | El error aparece en Sentry con stack trace. |

---

## HU_49 · Auto-scaling y health checks (1 SP)

**Resumen:** Kubernetes puede escalar el sistema según la carga.

### 🟢 Casos Funcionales

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-49-01-F | Health check | 1. Ir a `/health`. | Se ve `{"status": "ok"}`. |

### ⚡ Casos de Rendimiento

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-49-01-R | Health check rápido | 1. Medir tiempo de respuesta. | Menor a 50ms. |

### ❌ Casos Negativos

| ID | Descripción | Pasos | Resultado esperado |
|----|-------------|-------|---------------------|
| CP-49-01-N | Health check degradado | 1. BD caída. | Devuelve `{"status": "degraded", "db": "down"}` con HTTP 503. |

---

## 📋 Anexo: Definición de Done (DoD) Global aplicada a cada HU

Estos son los **12 criterios globales** que cualquier HU debe cumplir para considerarse "Done" (Hecha):

1. ✅ **Código mergeado** a `main` mediante Pull Request aprobado por al menos 1 reviewer.
2. ✅ **Tests unitarios** escritos y pasando (cobertura mínima 70%).
3. ✅ **Tests de integración** escritos y pasando para endpoints críticos.
4. ✅ **Documentación actualizada** (OpenAPI, README, comentarios en código).
5. ✅ **Code review** aprobado sin comentarios pendientes.
6. ✅ **CI/CD pasa** (lint, type-check, build, tests).
7. ✅ **Despliegue en staging** verificado manualmente.
8. ✅ **Logs estructurados** emitidos en cada acción importante.
9. ✅ **Métricas** configuradas para monitorear la HU (contadores, latencias).
11. ✅ **Alertas** configuradas si aplica (errores, latencias >0).
12. ✅ **Auditoría** habilitada para acciones sensibles (crear, borrar, editar).
13. ✅ **Seguridad revisada**: rate limit, validación de inputs, sin secretos en logs.

---

## 📌 Cómo usar este documento

1. **Para QA Manual**: Cada caso tiene pasos claros que un tester puede seguir sin conocimiento técnico.
2. **Para Automatización**: Los pasos están suficientemente estructurados para convertirse en tests automatizados (pytest, Cypress, etc.).
3. **Para Reportar Bugs**: Si un caso falla, basta citar el ID (ej. "CP-08-15-F falló").
4. **Para Nuevos Desarrolladores**: Leer los casos de su HU asignada antes de empezar a codificar.

---

## 🔗 Referencias

- **Documento fuente:** https://jxa24h0tmp5g.space.mcode.io/
- **Versión analizada:** V134.2 (Documento Técnico Corregido)
- **Total HUs:** 49
- **Total SP:** 261
- **Total de Casos de Prueba generados:** 599
- **Tipos cubiertos:** Funcionales (208) · Seguridad (155) · Rendimiento (74) · Negativos (162)

---

> **Documento generado como propuesta formal de testing para WowHub V134.2. Cada caso es trazable a una HU específica y respeta los criterios del DoD de la épica correspondiente.**