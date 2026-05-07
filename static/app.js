const state = {
    products: [],
    cart: [],
};

async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || "Request failed.");
    }
    return data;
}

function currency(value) {
    return `$${Number(value).toFixed(2)}`;
}

function renderProducts() {
    const container = document.getElementById("product-list");
    container.innerHTML = "";

    state.products.forEach((product) => {
        const card = document.createElement("article");
        card.className = "product-card";
        card.innerHTML = `
            <div class="price-row">
                <h3>${product.name}</h3>
                <span>${currency(product.price)}</span>
            </div>
            <p>${product.description}</p>
            <div class="price-row">
                <span>${product.category}</span>
                <span class="stock-badge">${product.stock} in stock</span>
            </div>
            <div class="product-actions">
                <input class="qty-input" type="number" min="1" value="1" aria-label="Quantity for ${product.name}">
                <button class="primary-button">Add to Cart</button>
            </div>
        `;

        const qtyInput = card.querySelector(".qty-input");
        card.querySelector("button").addEventListener("click", () => {
            addToCart(product.id, Number(qtyInput.value));
        });
        container.appendChild(card);
    });
}

function renderCart() {
    const container = document.getElementById("cart-items");
    const totalElement = document.getElementById("cart-total");
    container.innerHTML = "";

    if (state.cart.length === 0) {
        container.innerHTML = "<div class='cart-row'>Cart is empty. Add products from the catalog.</div>";
        totalElement.textContent = currency(0);
        return;
    }

    let total = 0;
    state.cart.forEach((item) => {
        const row = document.createElement("div");
        const lineTotal = item.price * item.quantity;
        total += lineTotal;
        row.className = "cart-row";
        row.innerHTML = `
            <div>
                <strong>${item.name}</strong><br>
                <small>${currency(item.price)} each</small>
            </div>
            <div class="cart-actions">
                <input class="qty-input" type="number" min="1" value="${item.quantity}" aria-label="Cart quantity for ${item.name}">
                <button class="ghost-button">Remove</button>
            </div>
        `;

        row.querySelector(".qty-input").addEventListener("change", (event) => {
            updateCartQuantity(item.product_id, Number(event.target.value));
        });
        row.querySelector("button").addEventListener("click", () => {
            removeFromCart(item.product_id);
        });
        container.appendChild(row);
    });

    totalElement.textContent = currency(total);
}

function renderRestock() {
    const select = document.getElementById("restock-product");
    const table = document.getElementById("stock-table");
    select.innerHTML = "";
    table.innerHTML = "";

    state.products.forEach((product) => {
        const option = document.createElement("option");
        option.value = product.id;
        option.textContent = `${product.name} (${product.stock} available)`;
        select.appendChild(option);

        const row = document.createElement("div");
        row.className = "stock-row";
        row.innerHTML = `
            <span>${product.name}</span>
            <span class="stock-badge">${product.stock} units</span>
        `;
        table.appendChild(row);
    });
}

async function refreshProducts() {
    state.products = await fetchJson("/api/products");
    renderProducts();
    renderRestock();
}

async function refreshDashboard() {
    const metrics = await fetchJson("/api/dashboard");
    document.getElementById("metric-products").textContent = metrics.total_products;
    document.getElementById("metric-orders").textContent = metrics.total_orders;
    document.getElementById("metric-stock").textContent = metrics.low_stock;
    document.getElementById("metric-revenue").textContent = currency(metrics.revenue);
}

async function refreshOrders() {
    const orders = await fetchJson("/api/orders");
    const container = document.getElementById("orders-list");
    container.innerHTML = "";

    if (orders.length === 0) {
        container.innerHTML = "<div class='history-item'>No orders yet.</div>";
        return;
    }

    orders.forEach((order) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.innerHTML = `
            <strong>#${order.id} - ${order.customer_name}</strong><br>
            <small>${currency(order.total)} • ${order.item_lines} item lines • ${order.created_at}</small>
        `;
        container.appendChild(item);
    });
}

function addToCart(productId, quantity) {
    if (quantity <= 0) {
        return;
    }

    const product = state.products.find((item) => item.id === productId);
    if (!product) {
        return;
    }

    const existing = state.cart.find((item) => item.product_id === productId);
    if (existing) {
        existing.quantity += quantity;
    } else {
        state.cart.push({
            product_id: product.id,
            name: product.name,
            price: product.price,
            quantity,
        });
    }

    renderCart();
}

function updateCartQuantity(productId, quantity) {
    if (quantity <= 0) {
        removeFromCart(productId);
        return;
    }

    const existing = state.cart.find((item) => item.product_id === productId);
    if (existing) {
        existing.quantity = quantity;
    }
    renderCart();
}

function removeFromCart(productId) {
    state.cart = state.cart.filter((item) => item.product_id !== productId);
    renderCart();
}

async function submitOrder(event) {
    event.preventDefault();
    const feedback = document.getElementById("order-feedback");
    feedback.textContent = "";

    try {
        const customerName = document.getElementById("customer-name").value.trim();
        const payload = {
            customer_name: customerName,
            items: state.cart.map((item) => ({
                product_id: item.product_id,
                quantity: item.quantity,
            })),
        };

        const result = await fetchJson("/api/orders", {
            method: "POST",
            body: JSON.stringify(payload),
        });

        feedback.textContent = `${result.message} Order #${result.order_id} created for ${currency(result.total)}.`;
        state.cart = [];
        document.getElementById("order-form").reset();
        renderCart();
        await Promise.all([refreshProducts(), refreshOrders(), refreshDashboard()]);
    } catch (error) {
        feedback.textContent = error.message;
    }
}

async function submitRestock(event) {
    event.preventDefault();
    const feedback = document.getElementById("restock-feedback");
    feedback.textContent = "";

    try {
        const productId = Number(document.getElementById("restock-product").value);
        const quantity = Number(document.getElementById("restock-quantity").value);
        const result = await fetchJson("/api/restock", {
            method: "POST",
            body: JSON.stringify({
                product_id: productId,
                quantity,
            }),
        });
        feedback.textContent = result.message;
        await Promise.all([refreshProducts(), refreshDashboard()]);
    } catch (error) {
        feedback.textContent = error.message;
    }
}

async function initializePage() {
    document.getElementById("refresh-products").addEventListener("click", refreshProducts);
    document.getElementById("order-form").addEventListener("submit", submitOrder);
    document.getElementById("restock-form").addEventListener("submit", submitRestock);

    renderCart();
    await Promise.all([refreshProducts(), refreshOrders(), refreshDashboard()]);
}

initializePage();
