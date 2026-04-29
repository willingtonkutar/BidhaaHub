# BidhaaHub Web App Project Guide

## 1. Project Vision
BidhaaHub is a web-based grocery inventory management platform designed to reduce stockouts, cut wastage, and improve supplier coordination for small and medium grocery stores.

Core outcomes:
- Real-time inventory visibility
- Automatic low-stock and expiry alerts
- Faster supplier ordering workflow
- Better reporting for business decisions

### In Simple Terms
BidhaaHub helps a store:
- Know what products are in stock right now
- Get warnings when items are running low
- Track expiry dates so food does not go bad
- Record sales and restocking automatically
- Manage suppliers in one place
- View reports to make better business decisions
- Accept and track payments using API integrations

Instead of using paper or guesswork, the shop uses one web app to control products, reduce losses, and keep customers happy.

## 2. Product Scope (MVP First)
Build the first version with only essential features, then expand.

### MVP Features
- User authentication (Admin, Manager, Staff, Supplier)
- Product and category management
- Supplier management
- Inventory transactions (restock, sale, adjustment, waste)
- Low-stock alerts and expiry alerts
- Dashboard with key metrics
- Basic report exports (CSV)
- API payment integration (diversified options: M-Pesa Daraja, card payments, bank transfer, and mobile wallets)

### Post-MVP Features
- Purchase order workflow and approval
- Supplier portal with delivery confirmations
- Barcode scanning integration
- Multi-branch support
- Forecasting and predictive reorder suggestions

## 3. Suggested Tech Stack

### Frontend
- React + Vite
- TypeScript
- Tailwind CSS (or plain CSS modules)
- TanStack Query for API state management

### Backend
- FastAPI (Python)
- SQLAlchemy ORM
- Pydantic for validation
- JWT authentication

### Database
- PostgreSQL (production)
- SQLite (local development only)

### DevOps
- Docker for local and deployment consistency
- GitHub Actions for CI (tests, linting)
- Render, Railway, or Fly.io for initial deployment

## 3.1 Easy Way to Run the App on Windows

If you just want to start the project quickly:

1. Open a terminal in the project folder.
2. Run the PowerShell launcher:

```powershell
.\run.ps1
```

If PowerShell scripts are blocked, use the batch file instead:

```bat
run.bat
```

The app will start on `http://127.0.0.1:8000`.

### Role-Based Login

The web app now starts with a login chooser:
- Customer: register or log in to browse the shop, cart, checkout, and My Orders
- Admin/staff: log in to manage products, suppliers, orders, delivery, and payment settings

Default admin credentials for local development:
- Email: `admin@bidhaahub.local`
- Password: `Admin123!`

Payment support is scaffolded through `POST /payments/initiate` with provider codes for `cash_on_delivery`, `mpesa_daraja`, `paypal`, and `mock_card`.

If you want to start it manually, use:

```powershell
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
