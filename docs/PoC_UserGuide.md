# Work Intake & Tracking — System Guide

## Overview

Work Intake & Tracking is a standalone web application built for the **Cloud Platform Engineering and Operations** organization. It provides a centralized system to accept, track, assign, and manage work requests across cloud infrastructure teams serving AWS, GCP, and Azure environments.

This application is the **system of record** for all work intake. There are no external ticketing system dependencies — everything is tracked here.

---

## User Roles

The system supports three roles with different levels of access:

| Role | Can Submit Requests | Can View Board | Can Assign/Edit All | Can Create Users/Groups | Can Delete Requests |
|------|--------------------:|:--------------:|:-------------------:|:-----------------------:|:-------------------:|
| **Submitter** | ✓ | ✓ | Own only | ✗ | ✗ |
| **Worker** | ✓ | ✓ | ✓ | ✗ | ✗ |
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## Authentication

### Logging In

1. Navigate to the application URL.
2. Enter your username and password on the login screen.
3. Click **Sign In**.

The system uses JWT-based authentication. Your session persists until you sign out or the token expires (default: 8 hours).

### Default Accounts (Development)

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | Admin |
| jdoe | password | Submitter |
| ssmith | password | Worker |

---

## The Dashboard

After logging in, you land on the **Board** view — a Kanban-style dashboard showing all work requests organized by status.

### Navigation

The top header provides navigation between three views:

- **Board** — Kanban board with all requests grouped by status columns
- **New Request** — Multi-step form to submit new work
- **Teams** — Organization structure and group membership management

### Header Controls

- **Theme Toggle** (sun/moon icon) — Switches between light and dark mode. Respects your OS preference by default and remembers your manual selection.
- **User Badge** — Shows your username and role.
- **Sign Out** — Ends your session.

---

## Kanban Board

The board displays work requests in columns by status:

**New** → **Triage** → **In Progress** → **Blocked** → **Completed** → **Cancelled**

### Cards

Each card displays:

- **WR Number** (e.g., WR-001) — Sequential identifier, clickable to open details
- **Title** — Clickable to open the detail view
- **Cloud Badge** — Color-coded indicator (AWS = orange, GCP = blue, Azure = cyan, Multi/Other = gray)
- **Priority Dot** — Color-coded severity (Low = gray, Medium = blue, High = yellow, Critical = red)
- **Description** — First 80 characters as a preview
- **Metadata** — Requester name, assigned group, assigned user
- **Reference URL** — Clickable link to external documentation (if provided)
- **Linked Items** — Badges showing attached epics, sprints, or tasks

### Card Actions

- **Assign** button — Opens the assignment modal
- **Status dropdown** — Quick-change the request status without opening details

### Drag and Drop

Cards can be **dragged between columns** to change status. Grab a card and drop it into a different status column. The target column highlights with a dashed border when you hover over it.

### Filtering and Search

Above the board is a **search bar** and **filters panel**:

- **Search** — Type to filter by title, description, or WR number (e.g., "WR-003" or "VPC")
- **Filters button** — Expands a panel with dropdown filters:
  - **Priority** — Filter by Low, Medium, High, or Critical
  - **Cloud** — Filter by AWS, GCP, Azure, or Multi/Other
  - **Group** — Filter by assigned group (or "Unassigned")
  - **Assignee** — Filter by assigned user (or "Unassigned")
- **Clear All** — Resets all active filters

Active filters are indicated by a dot badge on the Filters button.

---

## Submitting a New Request

Click **New Request** in the navigation to open the submission wizard. The form has four steps:

### Step 1: Details

| Field | Required | Description |
|-------|:--------:|-------------|
| Title | ✓ | Brief summary of the work needed (max 200 characters) |
| Description | | Detailed context, requirements, and acceptance criteria |
| Target Cloud | ✓ | Primary cloud platform: AWS, GCP, Azure, or Multi/Other |
| Priority | ✓ | Low, Medium, High, or Critical |
| Initial Status | | Admins can set to "Triage" directly; others always start at "New" |
| Reference URL | | Link to documentation, runbook, wiki, or cloud console page |

Each field includes help text explaining its purpose. URL fields validate format in real-time and show a preview when valid.

### Step 2: Assignment

| Field | Description |
|-------|-------------|
| Assigned Group | Route to a team or subgroup (hierarchical dropdown showing CFA, CORE, CPE and all subgroups) |
| Assigned User | Optionally assign directly to an individual |

Both fields are optional — you can assign later from the board or detail view.

### Step 3: Linked Items

Add epics, sprints, or tasks that relate to this request:

1. Select the item type (Epic, Sprint, or Task)
2. Enter a title
3. Optionally add a description
4. Click **Add**

Items appear in a preview list below. You can remove any item before submission. If you skip this step, linked items can always be added later from the request detail view.

### Step 4: Review

A summary of all fields you've entered. Review everything before submitting:

- All form fields displayed in a clean grid
- Linked items shown as color-coded badges
- Reference URL displayed as a clickable link

Click **Submit Request** to create. On success, you'll see a confirmation with the assigned WR number.

### After Submission

The success screen shows:

- ✓ Confirmation icon
- The assigned **WR number** (e.g., WR-007)
- The request title
- **Back to Board** — Return to the Kanban view
- **Create Another** — Reset the form to submit a new request

---

## Request Detail View

Click on any card's **WR number** or **title** to open the full detail panel. This is where you manage all aspects of a request.

### Viewing Details

The detail view shows all request fields:

- Status, Priority, Target Cloud
- Requester, Assigned Group, Assigned User
- Reference URL (clickable)
- Full description

### Editing a Request

1. Click **Edit Request** (visible to admins, workers, or the original requester)
2. All fields become editable:
   - Title, Description
   - Status, Priority, Target Cloud
   - Assigned Group (hierarchical picker)
   - Assigned User
   - Reference URL
3. Click **Save Changes** to persist, or **Cancel** to discard

### Managing Linked Items (Epics, Sprints, Tasks)

The bottom section of the detail view shows all linked items with full CRUD capabilities:

#### Adding Items
1. Click **+ Add Item**
2. Select type (Epic, Sprint, Task)
3. Enter title and optional description
4. Click **Add**

#### Editing Items
1. Click the ✏️ pencil icon on any item
2. Modify the type, title, or description inline
3. Click **Save** to persist

#### Deleting Items
1. Click the 🗑️ trash icon on any item
2. The item is immediately removed

---

## Assignment

### From the Board (Quick Assign)

1. Click the **Assign** button on any card
2. Choose **Assign to Group** or **Assign to User**
3. Select from the dropdown (groups are shown hierarchically)
4. Click **Confirm Assignment**

### From the Detail View

1. Open any request by clicking its title or WR number
2. Click **Edit Request**
3. Change the Assigned Group or Assigned User dropdowns
4. Click **Save Changes**

### At Submission Time

During the **Assignment** step of the intake form, you can pre-assign the request to a group and/or user before it's created.

---

## Teams & Organization

Click **Teams** in the navigation to view and manage the org structure.

### Organization Hierarchy

The teams view displays a tree of groups and subgroups:

```
Cloud Foundations & Automation (CFA)
├── Release and Delivery Engineering
├── Tools & Frameworks
├── Security, Risk and Compliance
└── AI Platform Engineering

Cloud Operations and Reliability Engineering (CORE)
├── SRE
├── FinOps
├── Architecture and Core Services
└── Observability

Cloud Product and Enablement (CPE)
├── Business Development Management (BDM)
├── Technical Program Management (TPM)
└── Technical Account Management (TAM)
```

Each group shows its member count and first few member names.

### Managing Group Membership (Admin Only)

1. Click **Manage Members** on any group or subgroup
2. A modal displays all users with checkboxes
3. Check/uncheck users to add or remove them from the group
4. Click **Save Members**

Users can belong to **multiple groups and subgroups** simultaneously.

### Creating Users (Admin Only)

1. Click **+ Add User** at the top of the Teams view
2. Fill in:
   - Username
   - Email
   - Password
   - Role (Submitter, Worker, or Admin)
3. Click **Create User**

The new user can immediately log in and be assigned to groups.

---

## Data Model

### Work Request Fields

| Field | Type | Description |
|-------|------|-------------|
| WR Number | Auto-generated | Sequential ID (WR-001, WR-002, ...) |
| Title | Text (200 max) | Brief summary |
| Description | Text | Detailed context and requirements |
| Target Cloud | Enum | AWS, GCP, Azure, or Multi/Other |
| Priority | Enum | Low, Medium, High, Critical |
| Status | Enum | New, Triage, In Progress, Blocked, Completed, Cancelled |
| Assigned Group | Reference | Team or subgroup responsible |
| Assigned User | Reference | Individual assignee |
| Reference URL | URL | Link to external documentation |
| Requester | Auto-set | The user who created the request |
| Created At | Timestamp | When the request was submitted |
| Updated At | Timestamp | Last modification time |

### Linked Items

| Field | Type | Description |
|-------|------|-------------|
| Type | Enum | Epic, Sprint, or Task |
| Title | Text | Name of the linked item |
| Description | Text | Additional context |

---

## Light & Dark Mode

The application supports both light and dark themes:

- **Light mode** — White surfaces, dark text, orange-700 Admin theme accents
- **Dark mode** — Dark surfaces, light text, orange-400 accents for readability

Toggle via the sun/moon icon in the header. The system respects your OS preference on first visit and remembers your manual choice.

---

## API Reference (For Integrations)

All data is accessible via REST endpoints at `/api/`:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/login | Authenticate and receive JWT token |
| GET | /api/auth/me | Get current user profile |
| GET | /api/users/ | List all users |
| POST | /api/users/ | Create a new user (admin) |
| GET | /api/groups/ | List all groups (flat) |
| GET | /api/groups/tree | Get hierarchical group tree with members |
| PUT | /api/groups/:id/members | Set group membership |
| GET | /api/work-requests/ | List all work requests |
| GET | /api/work-requests/:id | Get single request with linked items |
| POST | /api/work-requests/ | Create a work request |
| PATCH | /api/work-requests/:id | Update a work request |
| DELETE | /api/work-requests/:id | Delete a request (admin) |
| POST | /api/work-requests/:id/linked-items | Add a linked item |
| PATCH | /api/work-requests/:id/linked-items/:itemId | Update a linked item |
| DELETE | /api/work-requests/:id/linked-items/:itemId | Remove a linked item |

All endpoints (except login) require a Bearer token in the `Authorization` header.

---

## Running the Application Locally

### Prerequisites
- Python 3.9+
- Node.js 18+

### Start Backend
```bash
cd backend
pip3 install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Start Frontend
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and log in.

The database is automatically created and seeded with default users, groups, and org structure on first startup.
