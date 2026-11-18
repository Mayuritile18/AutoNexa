import os
import re
import html
import uuid

from functools import wraps
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_from_directory,
)

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


# =========================================================
# PATH CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent

load_dotenv(BASE_DIR / ".env")


# =========================================================
# FLASK CONFIGURATION
# =========================================================

app = Flask(
    __name__,
    template_folder=str(PROJECT_DIR),
    static_folder=None
)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "autonexa-secret-key"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:

    db_host = os.getenv(
        "DB_HOST",
        "localhost"
    )

    db_port = os.getenv(
        "DB_PORT",
        "5432"
    )

    db_user = os.getenv(
        "DB_USER",
        "postgres"
    )

    db_password = os.getenv(
        "DB_PASSWORD",
        ""
    )

    db_name = os.getenv(
        "DB_NAME",
        "autonexa"
    )

    if db_password:

        DATABASE_URL = (
            f"postgresql://{db_user}:{db_password}"
            f"@{db_host}:{db_port}/{db_name}"
        )

    else:

        raise RuntimeError(
            "DATABASE_URL is missing. "
            "Check backend/.env"
        )


def get_db():

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


# =========================================================
# HELPERS
# =========================================================

def safe(value):

    if value is None:
        return ""

    return html.escape(str(value))


def fmt_date(value):

    if not value:
        return "-"

    try:
        return value.strftime("%Y-%m-%d")

    except AttributeError:
        return str(value)


def money(value):

    if value is None:
        return "0.00"

    try:
        return f"{float(value):.2f}"

    except (TypeError, ValueError):
        return str(value)


def redirect_page(filename):

    return redirect(
        url_for(
            "page",
            filename=filename
        )
    )


# =========================================================
# TABLE RENDERING
# =========================================================

def replace_table_body(
    rendered_html,
    rows_html
):

    pattern = (
        r"(<table\b[^>]*>.*?"
        r"<tbody\b[^>]*>)"
        r".*?"
        r"(</tbody>.*?</table>)"
    )

    replacement = (
        r"\1"
        + rows_html
        + r"\2"
    )

    updated_html, count = re.subn(
        pattern,
        replacement,
        rendered_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL
    )

    if count == 0:

        print(
            "TABLE RENDER ERROR: "
            "<tbody> not found"
        )

    return updated_html


def replace_user_table(
    rendered_html,
    headers,
    rows_html
):

    header_html = ""

    for header in headers:

        header_html += (
            f"<th>{safe(header)}</th>"
        )

    if not rows_html:

        colspan = len(headers)

        rows_html = f"""
        <tr>
            <td
                colspan="{colspan}"
                style="text-align:center;"
            >
                No records found.
            </td>
        </tr>
        """

    new_table = f"""
    <thead>
        <tr>
            {header_html}
        </tr>
    </thead>

    <tbody>
        {rows_html}
    </tbody>
    """

    pattern = (
        r"(<table\b[^>]*>)"
        r".*?"
        r"(</table>)"
    )

    replacement = (
        r"\1"
        + new_table
        + r"\2"
    )

    updated_html, count = re.subn(
        pattern,
        replacement,
        rendered_html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL
    )

    return updated_html, count


def inject_records_table(
    rendered_html,
    title,
    headers,
    rows_html
):

    table_pattern = (
        r"<table\b[^>]*>.*?"
        r"</table>"
    )

    if re.search(
        table_pattern,
        rendered_html,
        flags=re.IGNORECASE | re.DOTALL
    ):

        updated_html, count = replace_user_table(
            rendered_html,
            headers,
            rows_html
        )

        if count:

            return updated_html

    header_html = ""

    for header in headers:

        header_html += (
            f"<th>{safe(header)}</th>"
        )

    if not rows_html:

        colspan = len(headers)

        rows_html = f"""
        <tr>
            <td
                colspan="{colspan}"
                style="text-align:center;"
            >
                No records found.
            </td>
        </tr>
        """

    table_html = f"""
    <section
        class="records-section"
        style="
            margin-top:30px;
            width:100%;
            overflow-x:auto;
        "
    >

        <h2 style="margin-bottom:15px;">
            {safe(title)}
        </h2>

        <div
            style="
                width:100%;
                overflow-x:auto;
            "
        >

            <table
                style="
                    width:100%;
                    border-collapse:collapse;
                "
            >

                <thead>
                    <tr>
                        {header_html}
                    </tr>
                </thead>

                <tbody>
                    {rows_html}
                </tbody>

            </table>

        </div>

    </section>
    """

    main_match = re.search(
        r"</main>",
        rendered_html,
        flags=re.IGNORECASE
    )

    if main_match:

        position = main_match.start()

        return (
            rendered_html[:position]
            + table_html
            + rendered_html[position:]
        )

    body_match = re.search(
        r"</body>",
        rendered_html,
        flags=re.IGNORECASE
    )

    if body_match:

        position = body_match.start()

        return (
            rendered_html[:position]
            + table_html
            + rendered_html[position:]
        )

    return rendered_html + table_html


# =========================================================
# AUTH DECORATORS
# =========================================================

def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:

            return redirect(
                url_for("root")
            )

        return view(
            *args,
            **kwargs
        )

    return wrapped


def user_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:

            return redirect(
                url_for("root")
            )

        if session.get("role") != "user":

            abort(403)

        return view(
            *args,
            **kwargs
        )

    return wrapped


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if "user_id" not in session:

            return redirect(
                url_for("root")
            )

        if session.get("role") != "admin":

            abort(403)

        return view(
            *args,
            **kwargs
        )

    return wrapped


# =========================================================
# AUTHENTICATION
# =========================================================

def authenticate_user(
    email,
    password,
    role
):

    email = (
        email or ""
    ).strip()

    password = (
        password or ""
    ).strip()

    role = (
        role or ""
    ).strip().lower()


    # =====================================================
    # ADMIN LOGIN
    # =====================================================

    if role == "admin":

        if not email or not password:

            return (
                None,
                "Please enter admin email and password."
            )

        try:

            with get_db() as conn:

                user = conn.execute(
                    """
                    SELECT
                        user_id,
                        name,
                        email,
                        phone,
                        password,
                        role,
                        status
                    FROM users
                    WHERE lower(email) = lower(%s)
                    LIMIT 1
                    """,
                    (email,)
                ).fetchone()

                if not user:

                    return (
                        None,
                        "Invalid admin email or password."
                    )

                db_role = (
                    user["role"] or ""
                ).strip().lower()

                db_status = (
                    user["status"] or ""
                ).strip().lower()

                if db_role != "admin":

                    return (
                        None,
                        "Invalid admin account."
                    )

                if db_status != "active":

                    return (
                        None,
                        "Admin account is inactive."
                    )

                stored_password = (
                    user["password"] or ""
                )

                try:

                    password_valid = (
                        check_password_hash(
                            stored_password,
                            password
                        )
                    )

                except (
                    ValueError,
                    TypeError
                ):

                    password_valid = False

                if not password_valid:

                    return (
                        None,
                        "Invalid admin email or password."
                    )

                print(
                    "ADMIN LOGIN SUCCESS:",
                    email
                )

                return (
                    user,
                    None
                )

        except Exception as error:

            print(
                "ADMIN LOGIN ERROR:",
                error
            )

            return (
                None,
                "Database error while logging in."
            )


    # =====================================================
    # USER / STAFF LOGIN
    # =====================================================

    if role == "user":

        staff_name = email.strip()

        if not staff_name:

            return (
                None,
                "Please enter staff name."
            )

        try:

            with get_db() as conn:

                with conn.transaction():

                    user = conn.execute(
                        """
                        SELECT
                            user_id,
                            name,
                            email,
                            phone,
                            password,
                            role,
                            status
                        FROM users
                        WHERE lower(name) = lower(%s)
                          AND lower(role) = 'user'
                        LIMIT 1
                        """,
                        (staff_name,)
                    ).fetchone()


                    # -------------------------------------
                    # NEW STAFF
                    # -------------------------------------

                    if not user:

                        internal_email = (
                            "staff_"
                            + uuid.uuid4().hex
                            + "@autonexa.local"
                        )

                        unique_phone = (
                            "9"
                            + uuid.uuid4().hex[:9]
                        )

                        placeholder_password = (
                            generate_password_hash(
                                "autonexa_staff"
                            )
                        )

                        user = conn.execute(
                            """
                            INSERT INTO users
                            (
                                name,
                                email,
                                phone,
                                password,
                                role,
                                status
                            )
                            VALUES
                            (
                                %s,
                                %s,
                                %s,
                                %s,
                                'user',
                                'active'
                            )
                            RETURNING
                                user_id,
                                name,
                                email,
                                phone,
                                password,
                                role,
                                status
                            """,
                            (
                                staff_name,
                                internal_email,
                                unique_phone,
                                placeholder_password
                            )
                        ).fetchone()

                        print(
                            "NEW STAFF USER CREATED:",
                            staff_name
                        )


                    # -------------------------------------
                    # EXISTING STAFF
                    # -------------------------------------

                    else:

                        db_status = (
                            user["status"] or ""
                        ).strip().lower()

                        if db_status != "active":

                            return (
                                None,
                                "This staff account is inactive."
                            )

                        print(
                            "EXISTING STAFF LOGIN:",
                            staff_name
                        )


                    # -------------------------------------
                    # ENSURE STAFF RECORD
                    # -------------------------------------

                    staff = conn.execute(
                        """
                        SELECT staff_id
                        FROM staff
                        WHERE user_id = %s
                        LIMIT 1
                        """,
                        (user["user_id"],)
                    ).fetchone()

                    if not staff:

                        conn.execute(
                            """
                            INSERT INTO staff
                            (
                                user_id,
                                designation,
                                experience,
                                status
                            )
                            VALUES
                            (
                                %s,
                                'Staff',
                                0,
                                'active'
                            )
                            """,
                            (user["user_id"],)
                        )

                    print(
                        "USER LOGIN SUCCESS:",
                        staff_name
                    )

                    return (
                        user,
                        None
                    )

        except Exception as error:

            print(
                "USER LOGIN ERROR:",
                error
            )

            return (
                None,
                "Database error while logging in."
            )

    return (
        None,
        "Invalid account type."
    )


def set_login_session(user):

    session.clear()

    session["user_id"] = user["user_id"]
    session["name"] = user["name"]

    session["role"] = (
        user["role"] or ""
    ).lower()


# =========================================================
# ROOT
# =========================================================

@app.route("/")
def root():

    if session.get("user_id"):

        if session.get("role") == "admin":

            return redirect_page(
                "admin-dashboard.html"
            )

        return redirect_page(
            "index.html"
        )

    return render_template(
        "login.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        login_value = request.form.get(
            "email",
            ""
        )

        password = request.form.get(
            "password",
            ""
        )

        role = request.form.get(
            "role",
            ""
        )

    else:

        login_value = request.args.get(
            "email",
            ""
        )

        password = request.args.get(
            "password",
            ""
        )

        role = request.args.get(
            "role",
            ""
        )

    user, error = authenticate_user(
        login_value,
        password,
        role
    )

    print(
        "LOGIN USER:",
        user
    )

    print(
        "LOGIN ERROR:",
        error
    )

    if error:

        flash(error)

        return redirect(
            url_for("root")
        )

    set_login_session(user)

    if session["role"] == "admin":

        return redirect_page(
            "admin-dashboard.html"
        )

    return redirect_page(
        "index.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect_page(
        "login.html"
    )


@app.route("/logout.html")
def logout_page():

    session.clear()

    return render_template(
        "logout.html"
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "GET":

        return render_template(
            "register.html"
        )

    name = request.form.get(
        "fullName",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    confirm_password = request.form.get(
        "confirmPassword",
        ""
    )

    designation = request.form.get(
        "designation",
        ""
    ).strip()

    experience_text = request.form.get(
        "experience",
        ""
    ).strip()

    if not all([
        name,
        email,
        phone,
        password,
        confirm_password,
        designation
    ]):

        flash(
            "Please fill all required fields."
        )

        return redirect(
            url_for("register")
        )

    if password != confirm_password:

        flash(
            "Passwords do not match."
        )

        return redirect(
            url_for("register")
        )

    match = re.search(
        r"\d+",
        experience_text
    )

    experience = (
        int(match.group())
        if match
        else 0
    )

    try:

        with get_db() as conn:

            with conn.transaction():

                password_hash = (
                    generate_password_hash(
                        password
                    )
                )

                user = conn.execute(
                    """
                    INSERT INTO users
                    (
                        name,
                        email,
                        phone,
                        password,
                        role,
                        status
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        'user',
                        'active'
                    )
                    RETURNING user_id
                    """,
                    (
                        name,
                        email,
                        phone,
                        password_hash
                    )
                ).fetchone()

                conn.execute(
                    """
                    INSERT INTO staff
                    (
                        user_id,
                        designation,
                        experience,
                        status
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        'active'
                    )
                    """,
                    (
                        user["user_id"],
                        designation,
                        experience
                    )
                )

    except psycopg.errors.UniqueViolation:

        flash(
            "Email already registered."
        )

        return redirect(
            url_for("register")
        )

    except Exception as error:

        print(
            "REGISTER ERROR:",
            error
        )

        flash(
            "Registration failed."
        )

        return redirect(
            url_for("register")
        )

    flash(
        "Registration successful. Please login."
    )

    return redirect(
        url_for("root")
    )


# =========================================================
# USER DASHBOARD
# =========================================================

@app.route("/index.html")
@user_required
def dashboard():

    try:

        with get_db() as conn:

            stats = {

                "customers": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM customers
                    """
                ).fetchone()["n"],

                "vehicles": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM vehicles
                    """
                ).fetchone()["n"],

                "services": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM services
                    """
                ).fetchone()["n"],

                "history": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM services
                    """
                ).fetchone()["n"]

            }

    except Exception as error:

        print(
            "DASHBOARD ERROR:",
            error
        )

        stats = {
            "customers": 0,
            "vehicles": 0,
            "services": 0,
            "history": 0
        }

    return render_template(
        "index.html",
        stats=stats
    )


# =========================================================
# CUSTOMER CREATE
# =========================================================

@app.route(
    "/customers",
    methods=["POST"]
)
@login_required
def create_customer():

    name = (
        request.form.get(
            "customerName"
        )
        or request.form.get("name")
        or ""
    ).strip()

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    email = (
        request.form.get(
            "email",
            ""
        ).strip().lower()
        or None
    )

    address = (
        request.form.get(
            "address",
            ""
        ).strip()
        or None
    )

    if not name or not phone:

        flash(
            "Customer name and phone are required."
        )

        return redirect_page(
            "customer.html"
        )

    try:

        with get_db() as conn:

            conn.execute(
                """
                INSERT INTO customers
                (
                    name,
                    phone,
                    email,
                    address,
                    created_by
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    name,
                    phone,
                    email,
                    address,
                    session["user_id"]
                )
            )

        flash(
            "Customer saved successfully."
        )

    except psycopg.errors.UniqueViolation:

        flash(
            "Customer already exists."
        )

    except Exception as error:

        print(
            "CUSTOMER ERROR:",
            error
        )

        flash(
            "Customer could not be saved."
        )

    return redirect_page(
        "customer.html"
    )



# =========================================================
# USER CUSTOMER PAGE
# =========================================================

@app.route("/customer.html")
@user_required
def user_customer_page():

    try:

        with get_db() as conn:

            customers = conn.execute(
                """
                SELECT
                    customer_id,
                    name,
                    phone,
                    email,
                    address
                FROM customers
                ORDER BY customer_id DESC
                """
            ).fetchall()

    except Exception as error:

        print(
            "CUSTOMER FETCH ERROR:",
            error
        )

        customers = []

    rows = ""

    for item in customers:

        rows += f"""
    <tr>

        <td>{safe(item["customer_id"])}</td>

        <td>{safe(item["name"])}</td>

        <td>{safe(item["phone"] or "-")}</td>

        <td>{safe(item["email"] or "-")}</td>

        <td>{safe(item["address"] or "-")}</td>

        <td>
            <form
                method="POST"
                action="/delete/customer/{safe(item['customer_id'])}"
                style="margin:0;"
                onsubmit="return confirm('Are you sure you want to delete this customer?');"
            >
                <button
                    type="submit"
                    style="
                        background:#dc3545;
                        color:white;
                        border:none;
                        padding:7px 12px;
                        border-radius:6px;
                        cursor:pointer;
                    "
                >
                    Delete
                </button>
            </form>
        </td>

    </tr>
    """
    page_html = render_template(
        "customer.html"
    )

    return inject_records_table(
    page_html,
    "Customer Records",
    [
        "Customer ID",
        "Customer Name",
        "Phone",
        "Email",
        "Address",
        "Delete"
    ],
    rows
)


# =========================================================
# VEHICLE CREATE
# =========================================================

@app.route(
    "/vehicles",
    methods=["POST"]
)
@login_required
def create_vehicle():

    customer_name = request.form.get(
        "customerName",
        ""
    ).strip()

    vehicle_number = request.form.get(
        "vehicleNumber",
        ""
    ).strip().upper()

    vehicle_type = request.form.get(
        "vehicleType",
        ""
    ).strip()

    brand = request.form.get(
        "brand",
        ""
    ).strip()

    model = request.form.get(
        "model",
        ""
    ).strip()

    manufacturing_year = request.form.get(
        "manufacturingYear",
        type=int
    )

    registration_date = (
        request.form.get(
            "registrationDate"
        )
        or None
    )

    if not all([
        customer_name,
        vehicle_number,
        vehicle_type,
        brand,
        model
    ]):

        flash(
            "Please fill all vehicle fields."
        )

        return redirect_page(
            "vehicle.html"
        )

    try:

        with get_db() as conn:

            customer = conn.execute(
                """
                SELECT customer_id
                FROM customers
                WHERE lower(name) = lower(%s)
                ORDER BY customer_id
                LIMIT 1
                """,
                (customer_name,)
            ).fetchone()

            if not customer:

                flash(
                    "Customer not found. Add customer first."
                )

                return redirect_page(
                    "vehicle.html"
                )

            conn.execute(
                """
                INSERT INTO vehicles
                (
                    owner_name,
                    vehicle_name,
                    vehicle_number,
                    service_date,
                    next_service_date,
                    customer_id,
                    vehicle_type,
                    brand,
                    model,
                    manufacturing_year,
                    registration_date
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    NULL,
                    NULL,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    customer_name,
                    f"{brand} {model}",
                    vehicle_number,
                    customer["customer_id"],
                    vehicle_type,
                    brand,
                    model,
                    manufacturing_year,
                    registration_date
                )
            )

        flash(
            "Vehicle saved successfully."
        )

    except psycopg.errors.UniqueViolation:

        flash(
            "Vehicle number already exists."
        )

    except Exception as error:

        print(
            "VEHICLE ERROR:",
            error
        )

        flash(
            "Vehicle could not be saved."
        )

    return redirect_page(
        "vehicle.html"
    )


# =========================================================
# USER VEHICLE PAGE
# =========================================================

@app.route("/vehicle.html")
@user_required
def user_vehicle_page():

    try:

        with get_db() as conn:

           vehicles = conn.execute(
    """
    SELECT

        v.id,

        COALESCE(
            c.name,
            v.owner_name
        ) AS customer_name,

        v.vehicle_number,
        v.vehicle_type,
        v.brand,
        v.model,
        v.manufacturing_year,
        v.registration_date

    FROM vehicles v

    LEFT JOIN customers c
        ON c.customer_id = v.customer_id

    ORDER BY v.id DESC
    """
).fetchall()

    except Exception as error:

        print(
            "VEHICLE FETCH ERROR:",
            error
        )

        vehicles = []

    rows = ""

    for item in vehicles:

        rows += f"""
        <tr>

            <td>{safe(item["id"])}</td>

            <td>
                {safe(item["customer_name"] or "-")}
            </td>

            <td>
                {safe(item["vehicle_number"])}
            </td>

            <td>
                {safe(item["vehicle_type"] or "-")}
            </td>

            <td>
                {safe(item["brand"] or "-")}
            </td>

            <td>
                {safe(item["model"] or "-")}
            </td>

            <td>
                {safe(
                    item["manufacturing_year"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["registration_date"]
                    )
                )}
            </td>


            <td>
    <form
        method="POST"
        action="/delete/vehicle/{safe(item['id'])}"
        style="margin:0;"
        onsubmit="return confirm('Are you sure you want to delete this vehicle?');"
    >
        <button
            type="submit"
            style="
                background:#dc3545;
                color:white;
                border:none;
                padding:7px 12px;
                border-radius:6px;
                cursor:pointer;
            "
        >
            Delete
        </button>
    </form>
</td>

        </tr>
        """

    page_html = render_template(
        "vehicle.html"
    )

    return inject_records_table(
        page_html,
        "Vehicle Records",
        [
            "Vehicle ID",
            "Customer",
            "Vehicle No.",
            "Type",
            "Brand",
            "Model",
            "Manufacturing Year",
            "Registration Date",
            "Last Service",
            "Next Service",
            "Delete"
        ],
        rows
    )


# =========================================================
# SERVICE CREATE
# =========================================================

@app.route(
    "/services",
    methods=["POST"]
)
@login_required
def create_service():

    vehicle_number = request.form.get(
        "vehicleNumber",
        ""
    ).strip().upper()

    service_date = request.form.get(
        "serviceDate"
    )

    service_type = request.form.get(
        "serviceType",
        ""
    ).strip()

    odometer = request.form.get(
        "odometer",
        type=int
    )

    work_done = request.form.get(
        "workDone",
        ""
    ).strip()

    work_cost = request.form.get(
        "workCost",
        type=float
    )

    payment_method = request.form.get(
        "paymentMethod",
        ""
    ).strip()

    payment_status = request.form.get(
        "paymentStatus",
        ""
    ).strip()

    service_status = request.form.get(
        "serviceStatus",
        ""
    ).strip()

    description = (
        request.form.get(
            "description",
            ""
        ).strip()
        or None
    )

    if not all([
        vehicle_number,
        service_date,
        service_type,
        work_done,
        payment_method,
        payment_status,
        service_status
    ]):

        flash(
            "Please fill all required service fields."
        )

        return redirect_page(
            "service.html"
        )

    if odometer is None or odometer < 0:

        flash(
            "Enter valid odometer kilometers."
        )

        return redirect_page(
            "service.html"
        )

    if work_cost is None or work_cost < 0:

        flash(
            "Enter valid service cost."
        )

        return redirect_page(
            "service.html"
        )

    if payment_method not in {
        "Cash",
        "UPI",
        "Card",
        "Net Banking"
    }:

        flash(
            "Invalid payment method."
        )

        return redirect_page(
            "service.html"
        )

    if payment_status not in {
        "Paid",
        "Pending"
    }:

        flash(
            "Invalid payment status."
        )

        return redirect_page(
            "service.html"
        )

    if service_status not in {
        "In Progress",
        "Completed",
        "Pending"
    }:

        flash(
            "Invalid service status."
        )

        return redirect_page(
            "service.html"
        )

    try:

        with get_db() as conn:

            with conn.transaction():

                vehicle = conn.execute(
                    """
                    SELECT id
                    FROM vehicles
                    WHERE upper(vehicle_number) = %s
                    LIMIT 1
                    """,
                    (vehicle_number,)
                ).fetchone()

                if not vehicle:

                    flash(
                        "Vehicle not found. "
                        "Add vehicle first."
                    )

                    return redirect_page(
                        "service.html"
                    )

                staff = conn.execute(
                    """
                    SELECT staff_id
                    FROM staff
                    WHERE user_id = %s
                    LIMIT 1
                    """,
                    (session["user_id"],)
                ).fetchone()

                if not staff:

                    staff = conn.execute(
                        """
                        INSERT INTO staff
                        (
                            user_id,
                            designation,
                            experience,
                            status
                        )
                        VALUES
                        (
                            %s,
                            'Staff',
                            0,
                            'active'
                        )
                        RETURNING staff_id
                        """,
                        (session["user_id"],)
                    ).fetchone()

                service = conn.execute(
                    """
                    INSERT INTO services
                    (
                        vehicle_id,
                        service_date,
                        service_type,
                        odometer_km,
                        status,
                        total_cost,
                        description,
                        created_by
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING service_id
                    """,
                    (
                        vehicle["id"],
                        service_date,
                        service_type,
                        odometer,
                        service_status,
                        work_cost,
                        description,
                        session["user_id"]
                    )
                ).fetchone()

                conn.execute(
                    """
                    INSERT INTO service_work
                    (
                        service_id,
                        staff_id,
                        work_description,
                        cost
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        service["service_id"],
                        staff["staff_id"],
                        work_done,
                        work_cost
                    )
                )

                conn.execute(
                    """
                    INSERT INTO payments
                    (
                        service_id,
                        amount,
                        payment_method,
                        payment_status,
                        payment_date
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        CURRENT_DATE
                    )
                    """,
                    (
                        service["service_id"],
                        work_cost,
                        payment_method,
                        payment_status
                    )
                )

                conn.execute(
                    """
                    UPDATE vehicles
                    SET service_date = %s
                    WHERE id = %s
                    """,
                    (
                        service_date,
                        vehicle["id"]
                    )
                )

        flash(
            "Service, work and payment saved successfully."
        )

    except Exception as error:

        print(
            "SERVICE ERROR:",
            error
        )

        flash(
            "Service could not be saved."
        )

    return redirect_page(
        "service.html"
    )


# =========================================================
# USER SERVICE PAGE
# =========================================================

@app.route("/service.html")
@user_required
def user_service_page():

    try:

        with get_db() as conn:

            services = conn.execute(
                """
                SELECT

                    s.service_id,

                    v.vehicle_number,

                    COALESCE(
                        c.name,
                        v.owner_name
                    ) AS customer_name,

                    s.service_date,
                    s.service_type,
                    s.odometer_km,

                    u.name AS staff_name,

                    sw.work_description,

                    s.total_cost,

                    p.payment_method,
                    p.payment_status,

                    s.status,
                    s.description

                FROM services s

                JOIN vehicles v
                    ON v.id = s.vehicle_id

                LEFT JOIN customers c
                    ON c.customer_id = v.customer_id

                LEFT JOIN service_work sw
                    ON sw.service_id = s.service_id

                LEFT JOIN staff st
                    ON st.staff_id = sw.staff_id

                LEFT JOIN users u
                    ON u.user_id = st.user_id

                LEFT JOIN payments p
                    ON p.service_id = s.service_id

                ORDER BY s.service_id DESC
                """
            ).fetchall()

    except Exception as error:

        print(
            "SERVICE FETCH ERROR:",
            error
        )

        services = []

    rows = ""

    for item in services:

        rows += f"""
        <tr>

            <td>
                S{safe(item["service_id"])}
            </td>

            <td>
                {safe(item["vehicle_number"])}
            </td>

            <td>
                {safe(
                    item["customer_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["service_date"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["service_type"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["odometer_km"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["staff_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["work_description"]
                    or "-"
                )}
            </td>

            <td>
                ₹{safe(
                    money(
                        item["total_cost"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["payment_method"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["payment_status"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["status"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["description"]
                    or "-"
                )}
            </td>

            <td>
    {safe(
        item["description"]
        or "-"
    )}
</td>

<td>
    <form
        method="POST"
        action="/delete/service/{safe(item['service_id'])}"
        style="margin:0;"
    >
        <button
            type="submit"
            style="
                background:#dc3545;
                color:white;
                border:none;
                padding:7px 12px;
                border-radius:6px;
                cursor:pointer;
            "
        >
            Delete
        </button>
    </form>
</td>

</tr>
"""


    page_html = render_template(
        "service.html"
    )

    return inject_records_table(
        page_html,
        "Service Records",
        [
            "Service ID",
            "Vehicle No.",
            "Customer",
            "Service Date",
            "Service Type",
            "KM",
            "Staff Name",
            "Work Done",
            "Cost",
            "Payment Method",
            "Payment Status",
            "Status",
            "Description",
            "Delete"
        ],
        rows
    )


# =========================================================
# HISTORY
# =========================================================

def get_history_rows():

    with get_db() as conn:

        return conn.execute(
            """
            SELECT

                s.service_id,

                v.vehicle_number,

                COALESCE(
                    c.name,
                    v.owner_name
                ) AS customer_name,

                s.service_date,
                s.service_type,
                s.odometer_km,

                u.name AS staff_name,

                sw.work_description,

                s.total_cost,

                p.payment_method,
                p.payment_status,

                s.status

            FROM services s

            JOIN vehicles v
                ON v.id = s.vehicle_id

            LEFT JOIN customers c
                ON c.customer_id = v.customer_id

            LEFT JOIN service_work sw
                ON sw.service_id = s.service_id

            LEFT JOIN staff st
                ON st.staff_id = sw.staff_id

            LEFT JOIN users u
                ON u.user_id = st.user_id

            LEFT JOIN payments p
                ON p.service_id = s.service_id

            ORDER BY
                s.service_date DESC,
                s.service_id DESC
            """
        ).fetchall()


@app.route("/history")
@user_required
def history_data():

    history = get_history_rows()

    rows = ""

    for item in history:

        rows += f"""
        <tr>

            <td>
                H{safe(item["service_id"])}
            </td>

            <td>
                {safe(item["vehicle_number"])}
            </td>

            <td>
                {safe(
                    item["customer_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["service_date"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["service_type"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["odometer_km"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["staff_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["work_description"]
                    or "-"
                )}
            </td>

            <td>
                ₹{safe(
                    money(
                        item["total_cost"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["payment_method"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["payment_status"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["status"]
                    or "-"
                )}
            </td>

        </tr>
        """

    page_html = render_template(
        "history.html"
    )

    return inject_records_table(
        page_html,
        "Service History",
        [
            "Service ID",
            "Vehicle No.",
            "Customer",
            "Service Date",
            "Service Type",
            "KM",
            "Staff Name",
            "Work Done",
            "Cost",
            "Payment Method",
            "Payment Status",
            "Status"
        ],
        rows
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin-dashboard.html")
@admin_required
def admin_dashboard():

    try:

        with get_db() as conn:

            stats = {

                "customers": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM customers
                    """
                ).fetchone()["n"],

                "vehicles": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM vehicles
                    """
                ).fetchone()["n"],

                "services": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM services
                    """
                ).fetchone()["n"],

                "staff": conn.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM staff
                    WHERE lower(status) = 'active'
                    """
                ).fetchone()["n"]

            }

    except Exception as error:

        print(
            "ADMIN DASHBOARD ERROR:",
            error
        )

        stats = {
            "customers": 0,
            "vehicles": 0,
            "services": 0,
            "staff": 0
        }

    return render_template(
        "admin-dashboard.html",
        stats=stats
    )


# =========================================================
# ADMIN CUSTOMER PAGE
# =========================================================

@app.route(
    "/admin-customers.html",
    methods=["GET", "POST"]
)
@admin_required
def admin_customers():

    if request.method == "POST":

        name = request.form.get(
            "customerName",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        email = (
            request.form.get(
                "email",
                ""
            ).strip().lower()
            or None
        )

        address = (
            request.form.get(
                "address",
                ""
            ).strip()
            or None
        )

        if not name or not phone:

            flash(
                "Customer name and phone are required."
            )

            return redirect_page(
                "admin-customers.html"
            )

        try:

            with get_db() as conn:

                conn.execute(
                    """
                    INSERT INTO customers
                    (
                        name,
                        phone,
                        email,
                        address,
                        created_by
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        name,
                        phone,
                        email,
                        address,
                        session["user_id"]
                    )
                )

            flash(
                "Customer added successfully."
            )

        except psycopg.errors.UniqueViolation:

            flash(
                "Customer already exists."
            )

        except Exception as error:

            print(
                "ADMIN CUSTOMER ERROR:",
                error
            )

            flash(
                "Customer could not be saved."
            )

        return redirect_page(
            "admin-customers.html"
        )

    try:

        with get_db() as conn:

            customers = conn.execute(
                """
                SELECT
                    customer_id,
                    name,
                    phone,
                    email,
                    address
                FROM customers
                ORDER BY customer_id DESC
                """
            ).fetchall()

    

    except Exception as error:

        print(
            "ADMIN CUSTOMER ERROR:",
            error
        )

        customers = []

    rows = ""

    for item in customers:

        rows += f"""
        <tr>

            <td>{safe(item["customer_id"])}</td>

            <td>{safe(item["name"])}</td>

            <td>{safe(item["phone"] or "-")}</td>

            <td>{safe(item["email"] or "-")}</td>

            <td>{safe(item["address"] or "-")}</td>

            <td>
                <form
                    method="POST"
                    action="/delete/customer/{safe(item['customer_id'])}"
                    style="margin:0;"
                    onsubmit="return confirm('Are you sure you want to delete this customer?');"
                >

                    <button
                        type="submit"
                        style="
                            background:#dc3545;
                            color:white;
                            border:none;
                            padding:7px 12px;
                            border-radius:6px;
                            cursor:pointer;
                        "
                    >
                        Delete
                    </button>

                </form>
            </td>

        </tr>
        """

    page_html = render_template(
        "admin-customers.html"
    )

    return replace_table_body(
        page_html,
        rows
    )


# =========================================================
# ADMIN VEHICLE PAGE
# =========================================================

@app.route("/admin-vehicles.html")
@admin_required
def admin_vehicles():

    try:

        with get_db() as conn:

            vehicles = conn.execute(
                """
                SELECT

                    v.id,

                    COALESCE(
                        c.name,
                        v.owner_name
                    ) AS customer_name,

                    v.vehicle_number,
                    v.vehicle_type,
                    v.brand,
                    v.model,
                    v.manufacturing_year,
                    v.registration_date,
                    v.service_date,
                    v.next_service_date

                FROM vehicles v

                LEFT JOIN customers c
                    ON c.customer_id = v.customer_id

                ORDER BY v.id DESC
                """
            ).fetchall()

    except Exception as error:

        print(
            "ADMIN VEHICLE ERROR:",
            error
        )

        vehicles = []

    rows = ""

    for item in vehicles:

        rows += f"""
        <tr>

            <td>
                {safe(item["id"])}
            </td>

            <td>
                {safe(
                    item["customer_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["vehicle_number"]
                )}
            </td>

            <td>
                {safe(
                    item["vehicle_type"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["brand"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["model"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["manufacturing_year"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["registration_date"]
                    )
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["service_date"]
                    )
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["next_service_date"]
                    )
                )}
            </td>

            <td>
    <form
        method="POST"
        action="/delete/vehicle/{safe(item['id'])}"
        style="margin:0;"
        onsubmit="return confirm('Are you sure you want to delete this vehicle?');"
    >
        <button
            type="submit"
            style="
                background:#dc3545;
                color:white;
                border:none;
                padding:7px 12px;
                border-radius:6px;
                cursor:pointer;
            "
        >
            Delete
        </button>
    </form>
</td>

        </tr>
        """

    page_html = render_template(
        "admin-vehicles.html"
    )

    return replace_table_body(
        page_html,
        rows
    )


# =========================================================
# ADMIN SERVICE PAGE
# =========================================================

@app.route("/admin-services.html")
@admin_required
def admin_services():

    try:

        with get_db() as conn:

            services = conn.execute(
                """
                SELECT

                    s.service_id,

                    v.vehicle_number,

                    COALESCE(
                        c.name,
                        v.owner_name
                    ) AS customer_name,

                    s.service_date,
                    s.service_type,
                    s.odometer_km,

                    u.name AS staff_name,

                    sw.work_description,

                    s.total_cost,

                    p.payment_method,
                    p.payment_status,

                    s.status

                FROM services s

                JOIN vehicles v
                    ON v.id = s.vehicle_id

                LEFT JOIN customers c
                    ON c.customer_id = v.customer_id

                LEFT JOIN service_work sw
                    ON sw.service_id = s.service_id

                LEFT JOIN staff st
                    ON st.staff_id = sw.staff_id

                LEFT JOIN users u
                    ON u.user_id = st.user_id

                LEFT JOIN payments p
                    ON p.service_id = s.service_id

                ORDER BY
                    s.service_id DESC
                """
            ).fetchall()

    except Exception as error:

        print(
            "ADMIN SERVICE ERROR:",
            error
        )

        services = []

    rows = ""

    for item in services:

        rows += f"""
        <tr>

            <td>
                S{safe(item["service_id"])}
            </td>

            <td>
                {safe(item["vehicle_number"])}
            </td>

            <td>
                {safe(
                    item["customer_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["service_date"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["service_type"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["staff_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["odometer_km"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["work_description"]
                    or "-"
                )}
            </td>

            <td>
                ₹{safe(
                    money(
                        item["total_cost"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["payment_method"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["payment_status"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["status"]
                    or "-"
                )}
            </td>

            <td>
    <form
        method="POST"
        action="/delete/service/{safe(item['service_id'])}"
        style="margin:0;"
        onsubmit="return confirm('Are you sure you want to delete this service record?');"
    >
        <button
            type="submit"
            style="
                background:#dc3545;
                color:white;
                border:none;
                padding:7px 12px;
                border-radius:6px;
                cursor:pointer;
            "
        >
            Delete
        </button>
    </form>
</td>

        </tr>
        """

    page_html = render_template(
        "admin-services.html"
    )

    return replace_table_body(
        page_html,
        rows
    )


# =========================================================
# ADMIN STAFF PAGE
# =========================================================

@app.route("/admin-staff.html")
@admin_required
def admin_staff():

    try:

        with get_db() as conn:

            staff_rows = conn.execute(
                """
                SELECT

                    s.staff_id,
                    u.name AS staff_name,
                    u.phone,
                    u.email,

                    s.designation,
                    s.experience,
                    s.status

                FROM staff s

                JOIN users u
                    ON u.user_id = s.user_id

                ORDER BY
                    s.staff_id DESC
                """
            ).fetchall()

    except Exception as error:

        print(
            "ADMIN STAFF ERROR:",
            error
        )

        staff_rows = []

    rows = ""

    for item in staff_rows:

        rows += f"""
        <tr>

            <td>
                {safe(item["staff_name"])}
            </td>

            <td>
                {safe(item["phone"] or "-")}
            </td>

            <td>
                {safe(item["email"] or "-")}
            </td>

            <td>
                {safe(
                    item["designation"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["experience"]
                    or 0
                )}
            </td>

            <td>
                {safe(
                    item["status"]
                    or "-"
                )}
            </td>

        </tr>
        """

    page_html = render_template(
        "admin-staff.html"
    )

    return replace_table_body(
        page_html,
        rows
    )


# =========================================================
# ADMIN HISTORY
# =========================================================

@app.route("/admin-history.html")
@admin_required
def admin_history():

    history = get_history_rows()

    rows = ""

    for item in history:

        rows += f"""
        <tr>

            <td>
                H{safe(item["service_id"])}
            </td>

            <td>
                {safe(item["vehicle_number"])}
            </td>

            <td>
                {safe(
                    item["customer_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    fmt_date(
                        item["service_date"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["service_type"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["odometer_km"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["staff_name"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["work_description"]
                    or "-"
                )}
            </td>

            <td>
                ₹{safe(
                    money(
                        item["total_cost"]
                    )
                )}
            </td>

            <td>
                {safe(
                    item["payment_method"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["payment_status"]
                    or "-"
                )}
            </td>

            <td>
                {safe(
                    item["status"]
                    or "-"
                )}
            </td>

        </tr>
        """

    page_html = render_template(
        "admin-history.html"
    )

    return replace_table_body(
        page_html,
        rows
    )

# =========================================================
# =========================================================
# DELETE RECORDS
# =========================================================

def delete_redirect(user_page, admin_page):

    if session.get("role") == "admin":

        return redirect_page(
            admin_page
        )

    return redirect_page(
        user_page
    )

@app.route(
    "/delete/customer/<int:customer_id>",
    methods=["POST"]
)
@login_required
def delete_customer(customer_id):

    try:

        with get_db() as conn:

            with conn.transaction():

                # -----------------------------------------
                # 1. Delete payments of this customer's services
                # -----------------------------------------

                conn.execute(
                    """
                    DELETE FROM payments
                    WHERE service_id IN (
                        SELECT service_id
                        FROM services
                        WHERE vehicle_id IN (
                            SELECT id
                            FROM vehicles
                            WHERE customer_id = %s
                        )
                    )
                    """,
                    (customer_id,)
                )

                # -----------------------------------------
                # 2. Delete service work
                # -----------------------------------------

                conn.execute(
                    """
                    DELETE FROM service_work
                    WHERE service_id IN (
                        SELECT service_id
                        FROM services
                        WHERE vehicle_id IN (
                            SELECT id
                            FROM vehicles
                            WHERE customer_id = %s
                        )
                    )
                    """,
                    (customer_id,)
                )

                # -----------------------------------------
                # 3. Delete services
                # -----------------------------------------

                conn.execute(
                    """
                    DELETE FROM services
                    WHERE vehicle_id IN (
                        SELECT id
                        FROM vehicles
                        WHERE customer_id = %s
                    )
                    """,
                    (customer_id,)
                )

                # -----------------------------------------
                # 4. Delete vehicles
                # -----------------------------------------

                conn.execute(
                    """
                    DELETE FROM vehicles
                    WHERE customer_id = %s
                    """,
                    (customer_id,)
                )

                # -----------------------------------------
                # 5. Delete customer
                # -----------------------------------------

                deleted = conn.execute(
                    """
                    DELETE FROM customers
                    WHERE customer_id = %s
                    """,
                    (customer_id,)
                )

                if deleted.rowcount == 0:

                    flash(
                        "Customer record not found."
                    )

                    return delete_redirect(
                        "customer.html",
                        "admin-customers.html"
                    )

        flash(
            "Customer and linked records deleted successfully."
        )

    except Exception as error:

        print(
            "DELETE CUSTOMER ERROR:",
            error
        )

        flash(
            "Customer could not be deleted."
        )

    return delete_redirect(
        "customer.html",
        "admin-customers.html"
    )


@app.route(
    "/delete/vehicle/<int:vehicle_id>",
    methods=["POST"]
)
@login_required
def delete_vehicle(vehicle_id):

    try:

        with get_db() as conn:

            with conn.transaction():

                service = conn.execute(
                    """
                    SELECT service_id
                    FROM services
                    WHERE vehicle_id = %s
                    LIMIT 1
                    """,
                    (vehicle_id,)
                ).fetchone()

                if service:

                    flash(
                        "Vehicle cannot be deleted because service history exists."
                    )

                    return delete_redirect(
                        "vehicle.html",
                        "admin-vehicles.html"
                    )

                deleted = conn.execute(
                    """
                    DELETE FROM vehicles
                    WHERE id = %s
                    """,
                    (vehicle_id,)
                )

                if deleted.rowcount == 0:

                    flash(
                        "Vehicle record not found."
                    )

                    return delete_redirect(
                        "vehicle.html",
                        "admin-vehicles.html"
                    )

        flash(
            "Vehicle deleted successfully."
        )

    except Exception as error:

        print(
            "DELETE VEHICLE ERROR:",
            error
        )

        flash(
            "Vehicle could not be deleted."
        )

    return delete_redirect(
        "vehicle.html",
        "admin-vehicles.html"
    )


@app.route(
    "/delete/service/<int:service_id>",
    methods=["POST"]
)
@login_required
def delete_service(service_id):

    try:

        with get_db() as conn:

            with conn.transaction():

                service = conn.execute(
                    """
                    SELECT service_id
                    FROM services
                    WHERE service_id = %s
                    LIMIT 1
                    """,
                    (service_id,)
                ).fetchone()

                if not service:

                    flash(
                        "Service record not found."
                    )

                    return delete_redirect(
                        "service.html",
                        "admin-services.html"
                    )

                conn.execute(
                    """
                    DELETE FROM payments
                    WHERE service_id = %s
                    """,
                    (service_id,)
                )

                conn.execute(
                    """
                    DELETE FROM service_work
                    WHERE service_id = %s
                    """,
                    (service_id,)
                )

                conn.execute(
                    """
                    DELETE FROM services
                    WHERE service_id = %s
                    """,
                    (service_id,)
                )

        flash(
            "Service record deleted successfully."
        )

    except Exception as error:

        print(
            "DELETE SERVICE ERROR:",
            error
        )

        flash(
            "Service record could not be deleted."
        )

    return delete_redirect(
        "service.html",
        "admin-services.html"
    )


# =========================================================
# USER / ADMIN PAGE ROUTE
# =========================================================

PUBLIC_PAGES = {
    "login.html",
    "register.html",
    "logout.html"
}

USER_PAGES = {
    "index.html",
    "customer.html",
    "vehicle.html",
    "service.html",
    "history.html"
}

ADMIN_PAGES = {
    "admin-dashboard.html",
    "admin-customers.html",
    "admin-vehicles.html",
    "admin-services.html",
    "admin-staff.html",
    "admin-history.html"
}


@app.route(
    "/<path:filename>",
    methods=["GET"]
)
def page(filename):

    # -----------------------------------------------------
    # IMPORTANT:
    # Do NOT allow CSS, JS, images or arbitrary files
    # through this route.
    # -----------------------------------------------------

    if not filename.endswith(".html"):

        abort(404)


    # -----------------------------------------------------
    # PUBLIC
    # -----------------------------------------------------

    if filename in PUBLIC_PAGES:

        return render_template(
            filename
        )


    # -----------------------------------------------------
    # USER
    # -----------------------------------------------------

    if filename in USER_PAGES:

        if "user_id" not in session:

            return redirect(
                url_for("root")
            )

        if session.get("role") != "user":

            abort(403)

        if filename == "index.html":

            return dashboard()

        if filename == "customer.html":

            return user_customer_page()

        if filename == "vehicle.html":

            return user_vehicle_page()

        if filename == "service.html":

            return user_service_page()

        if filename == "history.html":

            return history_data()

        return render_template(
            filename
        )


    # -----------------------------------------------------
    # ADMIN
    # -----------------------------------------------------

    if filename in ADMIN_PAGES:

        if "user_id" not in session:

            return redirect(
                url_for("root")
            )

        if session.get("role") != "admin":

            abort(403)

        if filename == "admin-dashboard.html":

            return admin_dashboard()

        if filename == "admin-customers.html":

            return admin_customers()

        if filename == "admin-vehicles.html":

            return admin_vehicles()

        if filename == "admin-services.html":

            return admin_services()

        if filename == "admin-staff.html":

            return admin_staff()

        if filename == "admin-history.html":

            return admin_history()

        return render_template(
            filename
        )


    abort(404)


# =========================================================
# CSS FILES
# =========================================================

@app.route("/style.css")
def style_css():

    css_file = PROJECT_DIR / "style.css"

    if not css_file.exists():

        abort(404)

    return send_from_directory(
        PROJECT_DIR,
        "style.css"
    )


@app.route("/admin-style.css")
def admin_style_css():

    css_file = (
        PROJECT_DIR
        / "admin-style.css"
    )

    if not css_file.exists():

        abort(404)

    return send_from_directory(
        PROJECT_DIR,
        "admin-style.css"
    )


# =========================================================
# IMAGES
# =========================================================

@app.route(
    "/images/<path:filename>"
)
def images(filename):

    images_dir = (
        PROJECT_DIR
        / "images"
    )

    return send_from_directory(
        images_dir,
        filename
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    try:

        with get_db() as conn:

            conn.execute(
                "SELECT 1"
            )

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception as error:

        return {
            "status": "error",
            "database": "disconnected",
            "message": str(error)
        }, 500


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(403)
def forbidden(error):

    return """
    <h1>403 - Access Denied</h1>
    <p>You do not have permission to access this page.</p>
    """, 403


@app.errorhandler(404)
def not_found(error):

    return """
    <h1>404 - Page Not Found</h1>
    <p>The requested page was not found.</p>
    """, 404


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )