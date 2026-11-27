# AssetTrack — Campus Equipment Borrowing System

AssetTrack is a Django web application for a university department that lends
laptops, projectors, cameras, microphones and other equipment to students and
faculty for academic activities. It replaces paper logs and spreadsheets with a
single auditable workflow backed by PostgreSQL (Supabase).

Users are split into two roles:

- **IT Admin (staff)** — maintains the equipment inventory and releases, receives
  and tracks borrowed equipment.
- **Employee (borrower)** — joins a company with a code, requests equipment and
  sees only their own loans and requests.

## Intended Features

The full system is intended to provide the following features. The first three
are the working Project Development 2 increment; the rest are planned for later
increments.

| # | Feature | Status |
| --- | --- | --- |
| 1 | Equipment and category inventory (Create / Read / Update / Delete) | Working |
| 2 | Borrowing transaction (request, staff approval, direct assignment) | Working |
| 3 | Return recording with actual return date and equipment condition | Working |
| 4 | Maintenance logging and resolution workflow | Planned |
| 5 | Usage / overdue reports dashboard | Planned |
| 6 | Company membership join and leave requests | Working |
| 7 | Admin-configurable self-checkout and overdue settings | Planned |

Accounts, roles, profiles and optional department management are implemented; departments are managed by IT Admins under **Departments** and can be assigned during registration, profile editing, or company member setup. Categories are managed under **Categories** with add, edit and protected deletion. Borrowing requests require an available company device or a new-model name, and record the purpose and request timestamp. Approval and direct assignment are transactional and reject any device that already has an active checkout.

## Core Feature — Equipment Borrowing Lifecycle (Vertical Slice)

The core feature is the **borrowing and returning of equipment**. It works end to
end through every layer of the system:

- **Database:** `Device`, `Category`, `Checkout` and `MaintenanceLog` models with
  migrations in `assets/migrations/`. Records use `ForeignKey` relationships to
  `accounts.User` (creator, borrower, approving staff) and `accounts.Company`.
  A checkout records the requested device or model, expected return date, actual
  return date and the condition of the equipment when returned.
- **Backend:** Django forms, views and URL routes in `assets/` implement inventory
  CRUD, checkout requests, approvals/rejections, direct assignment, returns and
  condition recording. Every view requires login and enforces role and company
  scoping.
- **Frontend:** Templates in `templates/assets/` and `templates/base.html` provide
  the clickable inventory table, add/edit/delete forms, request form, approval
  queue, active-loan table with a return-condition selector, and dashboards.

### Admin flow

1. Log in as an IT Admin and set up (or join) a company.
2. **Devices → Add Device** to stock equipment; use row **Edit** and **Delete**
   to maintain it. A device with checkout history cannot be deleted.
3. **Requests** to approve or reject employee requests. A request for a new model
   opens a prefilled Add Device form that fulfils it.
4. **Assign Device** for a direct staff-issued loan.
5. **Active Checkouts** → choose the return condition → **Mark Returned**. A
   damaged return automatically places the device Under Repair.

### Employee flow

1. Log in as an Employee and join a company using its code.
2. The employee dashboard shows active loans, pending requests and available pool.
3. **Request a Device** submits a request for an available item or for a new model.
4. Requests are linked to the employee (`Checkout.employee` and `created_by`),
   and employees only see their own records.

### Validation and business rules

- Required fields, unique asset tags and serial numbers, and date formats are
  validated by Django ModelForms; errors render inline with clear messages.
- A request must name an available device **or** a requested model name.
- Due dates cannot be in the past.
- Only available devices can be requested or assigned; returning a device makes
  it available again unless it was returned damaged.
- Devices with checkout history cannot be deleted.
- Cross-company record IDs are rejected, and employees cannot access admin pages.

## Standard Features (Project Development 1)

- Account registration (`/accounts/register/`)
- Login / logout (`/accounts/login/`, `/accounts/logout/`)
- Role-based dashboards (`/accounts/dashboard/admin/`,
  `/accounts/dashboard/employee/`)
- User profile view and edit (`/accounts/profile/`, `/accounts/profile/edit/`)
- Department management and assignment (`/assets/departments/`)

## Tech Stack

- Python 3.12+, Django 5.1.5
- PostgreSQL via Supabase (`psycopg[binary]`)
- `python-dotenv`, `Pillow`, Bootstrap 5 + Bootstrap Icons (CDN)

## Setup

1. Clone the repository and enter it:

   ```bash
   git clone https://github.com/vanderken/AssetTrack-Bucog-KenEdrian-G1.git
   cd AssetTrack-Bucog-KenEdrian-G1
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Create a Supabase project. In **Project Settings → Database → Connection
   string (Session pooler)** copy the connection details. Create a `.env` file in
   the project root (beside `manage.py`) with:

   ```env
   DJANGO_SECRET_KEY=replace-with-a-long-random-string
   DJANGO_DEBUG=True
   DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
   DB_NAME=postgres
   DB_USER=postgres.your-project-ref
   DB_PASSWORD=your-supabase-password
   DB_HOST=aws-1-xxx.pooler.supabase.com
   DB_PORT=6543
   ```

   Generate a secret key with
   `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
   The `.env` file is gitignored and must never be committed.

5. Apply migrations and start the server:

   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

   Open http://127.0.0.1:8000/ — you will be redirected to the login page.

6. Register one **IT Admin** and one **Employee** account through the UI. Log in
   as the admin to set up the company; employees join using the company code shown
   on the admin Company page.

7. Run the automated tests (an in-memory SQLite test database is used, so
   Supabase data is not affected):

   ```bash
   python manage.py test
   ```

## Test Accounts

| Role | Username | Password | Company |
| --- | --- | --- | --- |
| IT Admin | `admin_pd2` | `AssetTrack123!` | KMB |
| Employee | `employee_pd2` | `AssetTrack123!` | KMB |

## Documentation

- `docs/AssetTrack-Bucog-KenEdrian-G1-PD2.pdf` — Project Development 2
  Implementation / Completion Report.
- `docs/AssetTrack-Bucog-KenEdrian-G1-PD2-filled.docx` — editable report source.
