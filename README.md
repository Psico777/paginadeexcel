# EMFOX OMS - Order Management System
## Sistema de Procesamiento de Pedidos Inteligente

**Empresa:** EMFOX YIWU TRADE CO., LTD  
**Ruta:** Yiwu/Ningbo, China → Callao, Perú  
**Propósito:** Reducir el tiempo de entrada de datos manual de agentes en Yiwu

---

## 🏗 ARQUITECTURA DEL SISTEMA

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                      │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Image    │  │  Editable Table  │  │   Export     │  │
│  │  Upload   │→ │  (TanStack)      │→ │   Panel      │  │
│  │  Dropzone │  │  Real-time calc  │  │   .xlsx gen  │  │
│  └──────────┘  └──────────────────┘  └──────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/REST
┌──────────────────────▼──────────────────────────────────┐
│                   BACKEND (FastAPI)                       │
│  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐  │
│  │ Gemini AI    │  │ Business Logic │  │ Excel Export │  │
│  │ Vision       │→ │ CNY→USD conv   │→ │ EMFOX format│  │
│  │ Module       │  │ Totals calc    │  │ Template     │  │
│  └──────────────┘  └────────────────┘  └─────────────┘  │
└──────────────────────┬──────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │  Google Gemini  │
              │  2.5 Flash API  │
              │  (Vision)       │
              └─────────────────┘
```

### Flujo de Datos
```
Foto de producto → Gemini Vision AI → JSON estructurado → 
Business Logic (CNY→USD, totales) → Tabla Editable Web → 
Usuario edita → Exportación Excel (.xlsx formato EMFOX)
```

---

## 📊 ESQUEMA DE DATOS: Producto

```json
{
  "id": "uuid",
  "code": 10001,
  "articulo": "Peluche 1",
  "description": "25 cm sin relleno",
  "photo_url": "/uploads/abc.jpg",
  "quantity_cajas": 7,
  "quantity_total": 320,
  "cbm_unit": 1.0,
  "cbm_total": 0.55,
  "precio_unitario_cny": 11.0,
  "precio_unitario_usd": 1.53,
  "total_usd": 489.60,
  "tasa_cambio": 7.2,
  "editable": true
}
```

---

## 🚀 CÓMO EJECUTAR

### Prerrequisitos
- Python 3.10+
- Node.js 18+
- API Key de Google Gemini

### Backend
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Acceso
- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

---

## 📁 ESTRUCTURA DEL PROYECTO

```
Paginadeexcel/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app principal
│   │   ├── config.py            # Configuración (env vars)
│   │   ├── schemas.py           # Modelos Pydantic (ProductRow, etc.)
│   │   ├── routes.py            # Endpoints API
│   │   └── modules/
│   │       ├── __init__.py
│   │       ├── gemini_vision.py # Integración Gemini AI + System Prompt
│   │       ├── business_logic.py# Conversión moneda, cálculos, códigos
│   │       └── excel_export.py  # Generación Excel formato EMFOX
│   ├── uploads/                 # Imágenes subidas
│   ├── requirements.txt
│   └── .env                     # Variables de entorno
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx             # Entry point React
│   │   ├── App.jsx              # Componente raíz
│   │   ├── components/
│   │   │   ├── ImageUploader.jsx # Drag & drop de fotos
│   │   │   ├── EditableTable.jsx # Tabla editable (Excel web)
│   │   │   └── ExportPanel.jsx   # Panel exportación + datos consignatario
│   │   ├── services/
│   │   │   └── api.js           # Capa de comunicación con Backend
│   │   └── styles/
│   │       └── App.css          # Estilos (paleta EMFOX)
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
│
└── README.md
```

---

## 🤖 ESTRATEGIA DE VISIÓN (Gemini AI)

### System Prompt (Clave del Sistema)
El prompt instruye a Gemini para:

1. **Actuar como experto en logística** China→Perú
2. **Detectar productos individuales** en cada foto
3. **Leer texto manuscrito** asociado (precios en 元/YUAN, cantidades en UND, volúmenes en m³)
4. **Asociar datos** al producto correcto por proximidad visual
5. **Retornar JSON estructurado** con: descripción, precio CNY, cantidad, volumen, tamaño

### Formato de Datos Manuscritos Esperado
```
11元          → 11 Yuanes (precio unitario)
320 UND       → 320 unidades
0.55m³        → 0.55 metros cúbicos (total)
25cm          → 25 centímetros (tamaño)
```

### Nota sobre CBM
- `CBM UNIT` = volumen de 1 caja
- `CBMT (CBM TOTAL)` = CAJAS × CBM UNIT
- Ejemplo: 7 cajas × 3 m³/caja = 21 m³ total

---

## 💰 LÓGICA DE NEGOCIO

### Conversión de Moneda
```
USD = CNY / Tasa de Cambio
Ejemplo: 11 CNY / 7.2 = $1.53 USD
```
Tasa configurable en `.env` → `CNY_TO_USD_RATE=7.2`

### Cálculo de Totales
```
Total USD = Cantidad × Precio Unitario USD
Ejemplo: 320 × $1.53 = $489.60
```

### Códigos Secuenciales
Comienzan en 10001 y se incrementan: 10001, 10002, 10003...

---

## 📋 API ENDPOINTS

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/upload` | Subir imágenes |
| `POST` | `/api/upload-and-process` | Subir + procesar con IA |
| `POST` | `/api/recalculate` | Recalcular producto editado |
| `POST` | `/api/export` | Exportar a Excel |
| `GET` | `/api/config` | Obtener configuración |

---

## 📄 LICENCIA
Propiedad de EMFOX YIWU TRADE CO., LTD - Uso interno.
