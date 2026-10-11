
import gradio as gr
import sqlite3
import hashlib
from datetime import datetime

db = sqlite3.connect("ecommerce.db", check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS products(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT, price REAL, stock INTEGER)""")
db.execute("""CREATE TABLE IF NOT EXISTS users(
username TEXT PRIMARY KEY, password TEXT, role TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS orders(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT, items TEXT, total REAL,
status TEXT, created_at TEXT)""")

def hashed(p):
    return hashlib.sha256(p.encode()).hexdigest()

db.execute("INSERT OR IGNORE INTO users VALUES(?,?,?)",
           ("admin", hashed("admin123"), "Admin"))
db.execute("INSERT OR IGNORE INTO users VALUES(?,?,?)",
           ("user", hashed("user123"), "User"))

for n, p, s in [
    ("Headphones",799,20), ("Smart Watch",1499,15),
    ("Backpack",599,25), ("Mouse",399,30),
    ("Keyboard",699,18)
]:
    db.execute("""INSERT INTO products(name,price,stock)
    SELECT ?,?,? WHERE NOT EXISTS
    (SELECT 1 FROM products WHERE name=?)""", (n,p,s,n))
db.commit()

def get_products():
    rows = db.execute("SELECT * FROM products").fetchall()
    return "\n".join(
        f"ID:{r[0]} | {r[1]} | ₹{r[2]} | Stock:{r[3]}"
        for r in rows
    )

def login(u, p):
    row = db.execute(
        "SELECT role FROM users WHERE username=? AND password=?",
        (u.strip(), hashed(p))
    ).fetchone()
    if row:
        return f"Welcome {u}! Role: {row[0]}", {
            "username": u.strip(), "role": row[0]
        }
    return "Invalid username or password", None

def show_cart(cart):
    if not cart:
        return "Cart is empty"
    lines, total = [], 0
    for pid, qty in cart.items():
        r = db.execute(
            "SELECT name,price FROM products WHERE id=?", (pid,)
        ).fetchone()
        if r:
            subtotal = r[1] * qty
            total += subtotal
            lines.append(f"{r[0]} x {qty} = ₹{subtotal}")
    lines.append(f"Total = ₹{total}")
    return "\n".join(lines)

def add_cart(pid, qty, cart, session):
    cart = dict(cart or {})
    if not session:
        return cart, "Please login first", show_cart(cart)
    try:
        pid, qty = int(pid), int(qty)
    except (ValueError, TypeError):
        return cart, "Enter valid product ID and quantity", show_cart(cart)
    r = db.execute(
        "SELECT name,stock FROM products WHERE id=?", (pid,)
    ).fetchone()
    if not r or qty < 1:
        return cart, "Invalid product or quantity", show_cart(cart)
    if cart.get(pid, 0) + qty > r[1]:
        return cart, "Insufficient stock", show_cart(cart)
    cart[pid] = cart.get(pid, 0) + qty
    return cart, "Product added to cart", show_cart(cart)

def checkout(cart, session):
    cart = dict(cart or {})
    if not session:
        return cart, "Please login first", show_cart(cart)
    if not cart:
        return cart, "Cart is empty", show_cart(cart)

    items, total = [], 0
    for pid, qty in cart.items():
        r = db.execute(
            "SELECT name,price,stock FROM products WHERE id=?", (pid,)
        ).fetchone()
        if not r or qty > r[2]:
            return cart, "Insufficient stock", show_cart(cart)
        items.append(f"{r[0]} x {qty}")
        total += r[1] * qty

    cur = db.execute(
        "INSERT INTO orders(username,items,total,status,created_at) "
        "VALUES(?,?,?,?,?)",
        (session["username"], ", ".join(items), total,
         "Order Placed", datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    order_id = cur.lastrowid
    for pid, qty in cart.items():
        db.execute(
            "UPDATE products SET stock=stock-? WHERE id=?", (qty,pid)
        )
    db.commit()
    return {}, f"Order #{order_id} placed! Total ₹{total}", "Cart is empty"

def track_orders(session):
    if not session:
        return "Please login first"
    rows = db.execute(
        "SELECT id,items,total,status FROM orders WHERE username=?",
        (session["username"],)
    ).fetchall()
    return "\n\n".join(
        f"Order #{r[0]} | {r[1]} | ₹{r[2]} | {r[3]}" for r in rows
    ) or "No orders found"

def add_product(name, price, stock, session):
    if not session or session["role"] != "Admin":
        return "Admin login required", get_products()
    try:
        if not name.strip() or float(price) <= 0 or int(stock) < 0:
            raise ValueError
        db.execute(
            "INSERT INTO products(name,price,stock) VALUES(?,?,?)",
            (name.strip(),float(price),int(stock))
        )
        db.commit()
        return "Product added", get_products()
    except (ValueError, TypeError):
        return "Invalid product details", get_products()

def orders_list():
    rows = db.execute(
        "SELECT id,username,items,total,status FROM orders"
    ).fetchall()
    return "\n\n".join(
        f"Order #{r[0]} | {r[1]} | {r[2]} | ₹{r[3]} | {r[4]}"
        for r in rows
    ) or "No orders"

def update_order(oid, status, session):
    if not session or session["role"] != "Admin":
        return "Admin login required", orders_list()
    try:
        cur = db.execute(
            "UPDATE orders SET status=? WHERE id=?",
            (status,int(oid))
        )
        db.commit()
        return ("Status updated" if cur.rowcount else "Order not found"), orders_list()
    except (ValueError, TypeError):
        return "Invalid order ID", orders_list()

with gr.Blocks(title="E-Commerce Web Application") as app:
    gr.Markdown("# 🛍️ E-Commerce Web Application")
    gr.Markdown("Products | Cart | Checkout | Order Tracking")
    session = gr.State(None)
    cart = gr.State({})

    with gr.Tab("Login"):
        u = gr.Textbox(label="Username")
        p = gr.Textbox(label="Password", type="password")
        btn = gr.Button("Login")
        msg = gr.Textbox(label="Login Result")
        btn.click(login,[u,p],[msg,session])
        gr.Markdown("User: `user` / `user123`")
        gr.Markdown("Admin: `admin` / `admin123`")

    with gr.Tab("Products"):
        products = gr.Textbox(value=get_products(),label="Product Catalog",lines=8)
        gr.Button("Refresh").click(get_products,outputs=products)
        pid = gr.Number(label="Product ID",value=1,precision=0)
        qty = gr.Number(label="Quantity",value=1,precision=0)
        add = gr.Button("Add to Cart")
        result = gr.Textbox(label="Result")
        cart_box = gr.Textbox(label="Cart",lines=6)
        add.click(add_cart,[pid,qty,cart,session],[cart,result,cart_box])

    with gr.Tab("Checkout"):
        gr.Markdown("Add products from the Products tab first.")
        order = gr.Button("Place Order")
        order_result = gr.Textbox(label="Order Result")
        order.click(checkout,[cart,session],[cart,order_result,cart_box])

    with gr.Tab("Order Tracking"):
        track = gr.Button("Track Orders")
        tracking = gr.Textbox(label="My Orders",lines=8)
        track.click(track_orders,inputs=session,outputs=tracking)

    with gr.Tab("Admin Panel"):
        name = gr.Textbox(label="Product Name")
        price = gr.Number(label="Price",value=100)
        stock = gr.Number(label="Stock",value=10,precision=0)
        addp = gr.Button("Add Product")
        admin_msg = gr.Textbox(label="Result")
        catalog = gr.Textbox(label="Updated Catalog",lines=8)
        addp.click(add_product,[name,price,stock,session],[admin_msg,catalog])

        oid = gr.Number(label="Order ID",value=1,precision=0)
        status = gr.Dropdown(
            ["Order Placed","Processing","Shipped","Delivered"],
            value="Processing",label="Order Status")
        update = gr.Button("Update Order")
        update_msg = gr.Textbox(label="Update Result")
        order_list = gr.Textbox(label="All Orders",lines=8)
        update.click(update_order,[oid,status,session],[update_msg,order_list])

        gr.Button("Refresh Orders").click(orders_list,outputs=order_list)

if __name__ == "__main__":
    app.launch()
