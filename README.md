<div align="center">
  <img src="./web/assets/images/logo.png" alt="BidhaaHub Logo" width="120" height="120">
  <h1>BidhaaHub</h1>
  <p><strong>Smart Inventory Management for Fresh Produce & Grocery Stores</strong></p>
  
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
  [![Python](https://img.shields.io/badge/Python-3.13-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
  [![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-FCA121?style=flat-square)](https://www.sqlalchemy.org/)
  [![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
  [![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)]()
</div>

---

## 📋 Table of Contents
- [Overview](#overview)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Architecture](#architecture)
- [Payment Integration](#payment-integration)
- [API Documentation](#api-documentation)
- [Support](#support)

---

## 🎯 Overview

**BidhaaHub** is a comprehensive, all-in-one inventory and order management system built specifically for small and medium-sized grocery stores and fresh produce retailers in Kenya. It combines a powerful admin dashboard for inventory control with a modern customer-facing storefront for seamless shopping and delivery.

### The Problem We Solve
- **Stockouts** hurt revenue and frustrate customers
- **Wastage** from expired stock eats into margins
- **Manual tracking** is error-prone and time-consuming
- **Fragmented payments** complicate reconciliation
- **Poor visibility** makes business decisions guesswork

### Our Solution
BidhaaHub centralizes everything: products, suppliers, orders, payments, and analytics—all in one web platform that works on desktop and mobile.

---

## ✨ Key Features

### 👨‍💼 For Store Managers & Admins
- **📊 Real-Time Dashboard**
  - KPI cards: total orders, revenue, pending orders, low-stock alerts
  - 7-day sales trend chart
  - Order status doughnut chart
  - Recent orders list

- **📦 Inventory Management**
  - Add/edit/delete products with categories, prices, images
  - Barcode support for future scanning integration
  - Automatic low-stock alerts (<10 units)
  - Expiry date tracking with automatic alerts

- **🤝 Supplier Management**
  - Maintain supplier contact information
  - Track lead times for restocking
  - Supplier ordering workflow

- **📋 Order Management**
  - View all customer orders with statuses
  - Track payment status (Paid/Unpaid)
  - Update fulfillment status (Preparing → Out for Delivery → Delivered)
  - Emergency admin override for payment status (with audit logging)

- **💳 Payment Settings**
  - Stripe integration for card payments
  - M-Pesa (via Daraja) for mobile money
  - IntaSend for alternative gateways
  - PayPal support (scaffolded)
  - Cash on Delivery option

- **📊 Reports & Analytics**
  - Inventory value report
  - Sales by transaction type
  - Product-level insights
  - Expiring/expired items tracking

### 🛒 For Customers
- **🏪 Modern Shop Experience**
  - Browse products by category
  - Search and filter by name
  - View product details (image, price, stock level, expiry)
  - Real-time stock availability

- **🛍️ Shopping Cart**
  - Add/remove items
  - Adjust quantities
  - See live total with delivery fees

- **💳 Flexible Checkout**
  - Multiple payment methods (Card, M-Pesa, Cash on Delivery)
  - Delivery method selection (Pickup, Courier, Rider)
  - Real-time delivery fee calculation
  - Pre-filled address from profile

- **📦 Order Tracking**
  - View all personal orders with status
  - Download receipt as PDF
  - Track fulfillment (preparing → delivered)
  - Mark pickup/delivery completion

- **📄 PDF Receipts**
  - Professional receipt download
  - Includes order details, items, costs, delivery info
  - Support contact information

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **Backend** | FastAPI (Python 3.13), SQLAlchemy ORM |
| **Database** | SQLite (dev), PostgreSQL (production-ready) |
| **Auth** | JWT tokens, role-based access control |
| **Payments** | Stripe API, IntaSend, M-Pesa Daraja |
| **PDF Generation** | ReportLab |
| **Styling** | Dark theme with responsive design |
| **Deployment** | Docker-ready, CORS-enabled |

---

## 🚀 Quick Start

### Prerequisites
- **Windows/Mac/Linux** with terminal access
- **Python 3.13+** installed
- **pip** package manager

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/BidhaaHub.git
   cd BidhaaHub
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate
   
   # Mac/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**

   **Windows (Easiest):**
   ```powershell
   .\run.ps1
   ```
   
   Or with batch file:
   ```batch
   run.bat
   ```

   **Manual start:**
   ```bash
   cd BidhaaHub
   uvicorn app.main:app --reload
   ```

5. **Open in browser**
   ```
   http://127.0.0.1:8000
   ```

---

## 📖 Usage

### First Time Setup

#### Admin Account (Local Development)
```
Email: admin@bidhaahub.local
Password: Admin123!
```

### User Roles

| Role | Access | Permissions |
|------|--------|-------------|
| **Admin** | Full dashboard access | Create products, manage suppliers, view orders, payment settings, override payments (logged) |
| **Customer** | Storefront only | Browse shop, create cart, checkout, view own orders, download receipts |

### Typical Workflows

#### For Store Manager
1. ✅ Log in as admin
2. 📦 Add products: Dashboard → Products → "Add Product"
3. 🤝 Set up suppliers: Dashboard → Suppliers
4. 📊 Review dashboard: KPIs, charts, low-stock alerts
5. 📋 Process orders: Orders → Update status
6. 💳 Configure payments: Payment Settings → Enter API keys
7. 📊 Export reports: Reports → Download CSV

#### For Customer
1. 🔑 Register or log in as customer
2. 🛍️ Browse products: Shop page
3. 🛒 Add to cart: Click "Add to Cart" on products
4. 💳 Checkout: Review items → Select delivery → Choose payment
5. 💰 Pay: Use Stripe, M-Pesa, or Cash on Delivery
6. 📦 Track order: My Orders → View status
7. 📄 Download receipt: My Orders → "Download Receipt (PDF)"

---

## 🏗️ Architecture

### Frontend Structure
```
BidhaaHub/web/
├── index.html          # Single-page app (SPA)
├── assets/
│   ├── images/
│   │   ├── logo.png
│   │   └── popular/
│   └── videos/
```

### Backend Structure
```
BidhaaHub/app/
├── main.py             # FastAPI routes & business logic
├── models.py           # SQLAlchemy ORM models
├── schemas.py          # Pydantic validation schemas
├── database.py         # DB connection & session
├── security.py         # JWT, password hashing
└── __init__.py
```

### Database Models
- **Users**: Admin, staff, customers with roles
- **Products**: Inventory with categories, pricing, images
- **Orders**: Customer orders with items, status
- **Payments**: Payment records linked to orders
- **Suppliers**: Vendor information
- **CheckoutSessions**: Temporary shopping sessions
- **Transactions**: Ledger of sales/restocks/adjustments
- **Alerts**: Low-stock and expiry notifications
- **DeliveryOptions**: Delivery methods & fees

---

## 💳 Payment Integration

### Stripe (Card Payments)
- ✅ Implemented and tested
- Test card: `4242 4242 4242 4242`
- Automatic payment confirmation
- Webhook support for real-time updates

### IntaSend
- ✅ Scaffolded - alternative payment gateway
- Supports M-Pesa and other mobile money

### Cash on Delivery
- ✅ Implemented - no payment gateway needed
- Manual order confirmation

---

## 📡 API Documentation

### Authentication
All protected endpoints require JWT token in header:
```
Authorization: Bearer <your_jwt_token>
```

### Key Endpoints

#### Auth
- `POST /auth/register` - Create customer account
- `POST /auth/login` - Login (customer or admin)
- `GET /auth/me` - Get current user

#### Storefront (Public)
- `GET /storefront/products` - List products for shop

#### Orders
- `POST /checkout` - Create checkout session
- `POST /orders` - Create order from checkout
- `GET /orders/me` - Customer's own orders
- `GET /orders/{id}/receipt.pdf` - Download receipt as PDF
- `PATCH /orders/{id}/status` - Update order status
- `PATCH /orders/{id}/mark-received` - Mark as picked up/delivered

#### Products (Admin)
- `POST /products` - Create product
- `GET /products` - List products
- `PATCH /products/{id}` - Update product
- `DELETE /products/{id}` - Delete product

#### Suppliers (Admin)
- `POST /suppliers` - Create supplier
- `GET /suppliers` - List suppliers
- `PATCH /suppliers/{id}` - Update supplier
- `DELETE /suppliers/{id}` - Delete supplier

#### Payments (Admin)
- `GET /payments` - List all payments
- `POST /orders/{id}/force-mark-paid` - Emergency override (admin only, logged)

#### Dashboard (Admin)
- `GET /dashboard` - KPI summary
- `GET /reports/summary` - Full reports

Full API spec: `http://127.0.0.1:8000/docs` (Swagger UI)

---

## 🔐 Security Features

- ✅ **Password Hashing**: Bcrypt with salt
- ✅ **JWT Auth**: Stateless token-based authentication
- ✅ **Role-Based Access Control**: Admin, staff, customer roles
- ✅ **Request Validation**: Pydantic schemas on all inputs
- ✅ **CORS Enabled**: Secure cross-origin requests
- ✅ **Audit Logging**: Payment overrides logged for accountability
- ✅ **Payment Gateway Enforcement**: Payments validated by external providers first

---

## 📊 Screenshots & UI

### Admin Dashboard
- KPI cards with key metrics
- Real-time sales charts
- Order management interface
- Inventory alerts

### Customer Storefront
- Modern shop with categories
- Product detail view
- Shopping cart
- Checkout with multiple payment options
- Order tracking

### Payment Confirmations
- Professional PDF receipts
- Download & print support
- Delivery tracking info

---

## 🚀 Deployment

### Docker
```dockerfile
# Build image
docker build -t bidhaahub .

# Run container
docker run -p 8000:8000 bidhaahub
```

### Environment Variables (Production)
```
DATABASE_URL=postgresql://user:password@host/dbname
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
JWT_SECRET=your_secure_secret_key
```

---

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -m "Add my feature"`
4. Push to branch: `git push origin feature/my-feature`
5. Open a pull request

---

## 📞 Support

- 📧 **Email**: willykutar@gmail.com
- 📱 **Phone**: +254 792 063 636
- 🕐 **Hours**: 9am - 9pm Daily

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🎉 Acknowledgments

Built with ❤️ for Kenyan small business owners.

**BidhaaHub** - Smart inventory management for a smarter retail.

---

**Version**: 1.0.0 | **Last Updated**: May 2026
Set-Location "C:\Users\Administrator\Desktop\system development work\BidhaaHub"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

## 4. High-Level Architecture
- Client: Web dashboard for Admin/Manager/Staff + Supplier portal
- API: FastAPI REST endpoints handling business logic
- Data Layer: Relational database for products, suppliers, stock movement, and alerts
- Background Jobs: Scheduled checks for expiry and reorder suggestions

## 5. Recommended Folder Structure
Use this as your baseline:

```text
BidhaaHub/
	backend/
		app/
			api/
			core/
			models/
			schemas/
			services/
			main.py
		tests/
		requirements.txt
	frontend/
		src/
			components/
			pages/
			hooks/
			services/
			styles/
		package.json
	docs/
	.env.example
	docker-compose.yml
	README.md
```

## 6. Database Design (Initial)
Start with these entities:
- users: id, name, email, password_hash, role, created_at
- suppliers: id, name, contact_person, phone, email, lead_time_days
- products: id, name, category, barcode, unit_price, quantity, min_threshold, expiry_date, supplier_id
- transactions: id, product_id, type, quantity, unit_price, total_amount, created_at, user_id
- alerts: id, product_id, type, message, status, created_at

## 7. API Plan (MVP)

### Auth
- POST /auth/register
- POST /auth/login
- GET /auth/me

### Products
- GET /products
- POST /products
- PATCH /products/{id}
- DELETE /products/{id}

### Suppliers
- GET /suppliers
- POST /suppliers
- PATCH /suppliers/{id}

### Inventory Transactions
- POST /transactions
- GET /transactions

### Alerts and Dashboard
- GET /alerts
- PATCH /alerts/{id}/read
- GET /dashboard/summary

### Payments (API Integration)
- POST /payments/initiate
- POST /payments/callback
- GET /payments/{id}/status
- GET /payments/methods

## 8. Frontend Page Plan
- Login Page
- Create Account modal
- Dashboard Page
- Products Page (table + create/edit form + Expired Items filter)
- Suppliers Page
- Transactions Page
- Alerts Page
- Reports Page (includes expired items summary)
- Global footer component on all pages

## 9. Development Roadmap

### Phase 1: Planning and Setup (Week 1)
- Finalize requirements and acceptance criteria
- Create backend and frontend projects
- Set up linting, formatting, and environment files
- Define database schema and seed data

### Phase 2: Core Backend (Week 2)
- Build auth and role-based access control
- Implement products, suppliers, and transactions APIs
- Add validation and error handling
- Write unit tests for services and endpoints

### Phase 3: Core Frontend (Week 3)
- Build reusable layout and navigation
- Connect frontend to backend APIs
- Implement products/suppliers/transactions pages
- Add loading, error, and empty states

### Phase 4: Alerts and Reporting (Week 4)
- Add low-stock and expiry alerts
- Build dashboard metrics cards and charts
- Add CSV report export
- Improve UX and form validation

### Phase 5: Hardening and Deployment (Week 5)
- Add integration tests
- Security review (auth, input validation, permissions)
- Performance checks on list endpoints
- Deploy staging and production environments

## 10. Agile Workflow (How to Execute Daily)
- Use 1-week sprints
- Keep a product backlog with user stories
- Pick sprint goals (no more than 5 major tasks)
- Run daily standups (15 minutes)
- Demo completed work at end of sprint
- Run sprint retrospective and improve process

## 11. Quality and Testing Strategy

### Backend Testing
- Unit tests for business rules (stock updates, alerts)
- API tests for all endpoints
- Role/permission tests for protected routes

### Frontend Testing
- Component tests for forms and tables
- Integration tests for critical user flows

### Critical Flows to Test First
- Create product and assign supplier
- Record sale and verify stock deduction
- Trigger low-stock alert
- Export report data

## 12. Security Checklist
- Hash passwords using bcrypt/argon2
- Use JWT with expiry and refresh strategy
- Enforce role-based access controls on all sensitive routes
- Validate and sanitize all inputs
- Rate limit login endpoint
- Store secrets in environment variables only
- Enable HTTPS in production

## 13. Performance Targets
- API response under 3 seconds under normal load
- Sales transaction processing under 2 seconds
- Dashboard summary load under 2 seconds
- Support 100 concurrent active users for MVP

## 14. Definition of Done
A feature is complete only if:
- Business logic is implemented
- Automated tests pass
- Error handling is in place
- Access control is enforced
- Documentation is updated
- Feature is demo-ready

## 15. Immediate Next Steps
1. Initialize backend and frontend folders using the structure above.
2. Implement auth, products, and suppliers first.
3. Build dashboard and transactions page next.
4. Add alert automation and report exports.
5. Deploy a staging version and gather feedback before full release.

This plan gives you a practical path from idea to a production-ready web app with clear phases and priorities.

## 16. Latest Frontend Changes (April 2026)

The current frontend is implemented in `web/index.html` as a tabbed workspace over the FastAPI backend.

### Implemented UI and UX Improvements
- Accessible sidebar menu toggle:
	- `Menu` button now toggles sidebar open/close state.
	- Includes `aria-expanded` and `aria-controls` attributes.
	- Supports keyboard toggle with Enter/Space and `Ctrl/Cmd + M`.
	- Mobile behavior uses a drawer-style sidebar with backdrop overlay.
- Homepage improvements:
	- Added a more descriptive Home page headline and product-purpose description.
	- Added an About section explaining what the platform does and how to use the page.
	- Kept KPI cards and recent activity preview on the Home page.
- Breadcrumb navigation:
	- Dynamic breadcrumbs now reflect current module.
	- Multi-step style path shown for Add Product.
- Theme system:
	- Dark/Light mode toggle with saved preference in local storage.
- Micro-interactions:
	- Improved hover/focus/active animations on buttons and table rows.
- Toast notifications:
	- Dismissible success/error toasts for key user actions and errors.
- Product workflows:
	- Add Product form with inline validations:
		- no negative quantity/threshold
		- no past expiry date
		- duplicate barcode prevention
	- Products listing now includes client-side pagination.
- Supplier workflows:
	- Inline supplier phone validation.
	- Supplier metrics cards (total suppliers, average lead time).
	- Contact shortcuts in table: call, email, WhatsApp.
- Currency update:
	- All money formatting now uses Kenyan currency (`KES`, shown as `Ksh`).

### Existing Functional Modules
- Home (descriptive + KPI + about)
- Products (search/filter/list/pagination)
- Add Product (validated form)
- Suppliers (create/list/metrics/contact shortcuts)
- Reports (summary cards)

### Planned Next Enhancements
- Trend charts for sales/restocks/wastage
- Export options (CSV/PDF/Excel)
- Role-based UI behavior and audit logs
- Offline caching and advanced performance optimization (lazy load/virtualization)
- i18n support (English/Swahili)
