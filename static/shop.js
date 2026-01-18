// Global promo configuration
const GLOBAL_PROMO = {
    enabled: true,
    discountPercent: 15,
    label: "🔥 15% OFF SITEWIDE"
};

// Loyalty system configuration
const LOYALTY_CONFIG = {
    itemsRequired: 5,
    rewardType: 'cheapest_free'
};

const CATEGORY_EMOJIS = {
    coins: '🪙',
    bpcoins: '🎫',
    emote: '😀',
    premium: '👑',
    lootbox: '🎁',
    rolecards: '🎴',
    calendar: '📅',
    bundles: '📦'
};

let currentCategory = 'all';
let selectedProduct = null;
let cart = [];
let appliedCoupon = null;
let shopData = null; // Store fetched shop data

// Fetch shop data from API on page load
async function fetchShopData() {
    try {
        const response = await fetch('/api/shop/data');
        const data = await response.json();
        
        if (data.error) {
            showNotification('❌ ' + data.error, 'error');
            return null;
        }
        
        shopData = data;
        console.log('✅ Shop data loaded:', shopData);
        return data;
    } catch (error) {
        console.error('Failed to fetch shop data:', error);
        showNotification('❌ Failed to load shop data', 'error');
        return null;
    }
}

function getAllProducts() {
    if (!shopData) return [];
    
    const products = [];
    
    // Add bundles from database
    if (shopData.bundles) {
        shopData.bundles.forEach(bundle => {
            products.push({
                ...bundle,
                category: 'bundles',
                imageUrl: bundle.image ? `https://cdn2.wolvesville.com/promos/${bundle.image}@2x.jpg` : null
            });
        });
    }
    
    // Add skin sets
    if (shopData.skin_sets) {
        shopData.skin_sets.forEach(skinSet => {
            products.push({
                ...skinSet,
                category: 'bundles',
                name: skinSet.name,
                imageUrl: null
            });
        });
    }
    
    // Add daily skins
    if (shopData.daily_skins) {
        shopData.daily_skins.forEach(skin => {
            products.push({
                ...skin,
                category: 'bundles',
                name: skin.name,
                imageUrl: skin.imageName ? `https://cdn2.wolvesville.com/avatarItems/${skin.imageName}.png` : null
            });
        });
    }
    
    // Add calendars
    if (shopData.calendars) {
        shopData.calendars.forEach(cal => {
            products.push({
                type: 'CALENDAR',
                id: cal.id,
                name: cal.title,
                price: cal.price,
                cost: cal.cost,
                category: 'calendar',
                description: cal.description,
                imageUrl: cal.imageName ? `https://cdn2.wolvesville.com/calendars/${cal.imageName}.png` : null
            });
        });
    }
    
    return products;
}

function renderProducts(category = 'all') {
    const productsContainer = document.getElementById('products');
    
    if (!shopData) {
        productsContainer.innerHTML = `
            <div class="empty-state">
                <div class="icon">⏳</div>
                <div>Loading shop data...</div>
            </div>
        `;
        return;
    }
    
    const allProducts = getAllProducts();
    
    if (allProducts.length === 0) {
        productsContainer.innerHTML = `
            <div class="empty-state">
                <div class="icon">📦</div>
                <div>No products available yet</div>
            </div>
        `;
        return;
    }
    
    const filtered = category === 'all' 
        ? allProducts 
        : allProducts.filter(p => p.category === category);

    if (filtered.length === 0) {
        productsContainer.innerHTML = `
            <div class="empty-state">
                <div class="icon">${CATEGORY_EMOJIS[category] || '📦'}</div>
                <div>No ${category} items available</div>
            </div>
        `;
        return;
    }

    productsContainer.innerHTML = filtered.map(product => {
        // Best value badge
        let badgeHTML = '';
        if (product.isBestValue) {
            badgeHTML = '<div style="position:absolute;top:10px;right:10px;background:linear-gradient(135deg,var(--gold),#ffa500);color:#000;padding:6px 12px;border-radius:20px;font-weight:700;font-size:0.75rem;box-shadow:0 4px 15px rgba(255,215,0,0.4)">🔥 BEST VALUE</div>';
        }
        
        // New badge
        if (product.isNew) {
            badgeHTML += '<div style="position:absolute;top:10px;left:10px;background:linear-gradient(135deg,#ff6b6b,#ee5a6f);color:#fff;padding:6px 12px;border-radius:20px;font-weight:700;font-size:0.75rem;box-shadow:0 4px 15px rgba(255,107,107,0.4)">🆕 NEW</div>';
        }
        
        return `
            <div class="product-card" style="position:relative">
                ${badgeHTML}
                <div class="category-emoji">${CATEGORY_EMOJIS[product.category] || '📦'}</div>
                ${product.imageUrl ? `<img class="product-image" src="${product.imageUrl}" alt="${product.name}" onerror="this.style.display='none'">` : ''}
                <div class="product-name">${product.name || product.title}</div>
                ${product.description ? `<div style="color:var(--muted);font-size:0.9rem;margin-bottom:10px;text-align:center">${product.description}</div>` : ''}
                <div class="product-price">€${product.price.toFixed(2)}</div>
                <button class="buy-button" onclick='addToCart(${JSON.stringify(product).replace(/'/g, "&apos;")})'>
                    🛒 Add to Cart
                </button>
            </div>
        `;
    }).join('');
}

function addToCart(product) {
    const existingIndex = cart.findIndex(item => 
        item.type === product.type || 
        (item.id && item.id === product.id)
    );
    
    if (existingIndex >= 0) {
        cart[existingIndex].quantity += 1;
    } else {
        cart.push({
            ...product,
            quantity: 1
        });
    }
    
    updateCartDisplay();
    showNotification('✅ Added to cart!');
}

function removeFromCart(index) {
    cart.splice(index, 1);
    updateCartDisplay();
}

function updateCartQuantity(index, change) {
    cart[index].quantity += change;
    
    if (cart[index].quantity <= 0) {
        removeFromCart(index);
    } else {
        updateCartDisplay();
    }
}

function calculateTotal() {
    const round2 = (num) => Math.round(num * 100) / 100;
    
    const subtotal = round2(cart.reduce((sum, item) => sum + (item.price * item.quantity), 0));
    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    
    let loyaltyDiscount = 0;
    let freeItemsCount = Math.floor(totalItems / LOYALTY_CONFIG.itemsRequired);
    
    if (freeItemsCount > 0) {
        const sortedCart = [...cart].sort((a, b) => a.price - b.price);
        let itemsFreed = 0;
        
        for (let item of sortedCart) {
            const itemsToFree = Math.min(item.quantity, freeItemsCount - itemsFreed);
            loyaltyDiscount += item.price * itemsToFree;
            itemsFreed += itemsToFree;
            
            if (itemsFreed >= freeItemsCount) break;
        }
        loyaltyDiscount = round2(loyaltyDiscount);
    }
    
    let promoDiscount = 0;
    if (GLOBAL_PROMO.enabled) {
        promoDiscount = round2((subtotal - loyaltyDiscount) * (GLOBAL_PROMO.discountPercent / 100));
    }
    
    let couponDiscount = 0;
    if (appliedCoupon) {
        couponDiscount = round2((subtotal - loyaltyDiscount - promoDiscount) * (appliedCoupon.discount_percent / 100));
    }
    
    return {
        subtotal: subtotal,
        loyaltyDiscount: loyaltyDiscount,
        promoDiscount: promoDiscount,
        couponDiscount: couponDiscount,
        total: round2(Math.max(0, subtotal - loyaltyDiscount - promoDiscount - couponDiscount)),
        totalItems: totalItems,
        freeItemsCount: freeItemsCount
    };
}

function updateCartDisplay() {
    const cartBtn = document.getElementById('cartButton');
    const cartCount = document.getElementById('cartCount');
    const cartItems = document.getElementById('cartItems');
    const cartSummary = document.getElementById('cartSummary');
    
    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    
    if (totalItems > 0) {
        cartCount.textContent = totalItems;
        cartCount.style.display = 'flex';
    } else {
        cartCount.style.display = 'none';
    }
    
    if (cart.length === 0) {
        cartItems.innerHTML = '<div class="empty-cart">🛒 Your cart is empty</div>';
        cartSummary.style.display = 'none';
    } else {
        const totals = calculateTotal();
        
        let freeItemsRemaining = totals.freeItemsCount;
        const sortedCart = [...cart].map((item, idx) => ({...item, originalIndex: idx}))
            .sort((a, b) => a.price - b.price);
        
        const freeItemIndices = new Set();
        for (let item of sortedCart) {
            const itemsToFree = Math.min(item.quantity, freeItemsRemaining);
            if (itemsToFree > 0) {
                freeItemIndices.add(item.originalIndex);
            }
            freeItemsRemaining -= itemsToFree;
            if (freeItemsRemaining <= 0) break;
        }
        
        cartItems.innerHTML = cart.map((item, index) => {
            const isFree = freeItemIndices.has(index);
            const freeLabel = isFree ? '<span style="background:linear-gradient(135deg,var(--success),#20bf55);color:#fff;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:700;margin-left:8px">🎁 FREE</span>' : '';
            
            return `
                <div class="cart-item">
                    <div class="cart-item-info">
                        <div class="cart-item-name">${item.name}${freeLabel}</div>
                        <div class="cart-item-price">€${item.price.toFixed(2)}</div>
                    </div>
                    <div class="cart-item-controls">
                        <button onclick="updateCartQuantity(${index}, -1)" class="qty-btn">−</button>
                        <span class="cart-item-qty">${item.quantity}</span>
                        <button onclick="updateCartQuantity(${index}, 1)" class="qty-btn">+</button>
                        <button onclick="removeFromCart(${index})" class="remove-btn">🗑️</button>
                    </div>
                </div>
            `;
        }).join('');
        
        const progress = (totals.totalItems % LOYALTY_CONFIG.itemsRequired);
        const progressPercent = (progress / LOYALTY_CONFIG.itemsRequired) * 100;
        const itemsUntilFree = LOYALTY_CONFIG.itemsRequired - progress;
        
        const loyaltyHTML = `
            <div style="background:linear-gradient(135deg,rgba(123,75,255,0.15),rgba(123,75,255,0.05));border:1px solid rgba(123,75,255,0.3);border-radius:12px;padding:15px;margin-bottom:15px">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                    <div style="font-weight:700;color:#7b4bff">🎁 Loyalty Reward</div>
                    <div style="color:var(--muted);font-size:0.9rem">${progress} / ${LOYALTY_CONFIG.itemsRequired} items</div>
                </div>
                <div style="background:rgba(0,0,0,0.3);height:8px;border-radius:10px;overflow:hidden;margin-bottom:8px">
                    <div style="background:linear-gradient(90deg,#7b4bff,var(--accent));height:100%;width:${progressPercent}%;transition:width 0.3s"></div>
                </div>
                <div style="color:var(--muted);font-size:0.85rem">
                    ${totals.freeItemsCount > 0 ? 
                        `<span style="color:var(--success);font-weight:600">✨ ${totals.freeItemsCount} free item${totals.freeItemsCount > 1 ? 's' : ''} unlocked!</span>` : 
                        `${itemsUntilFree} more item${itemsUntilFree > 1 ? 's' : ''} until free item!`
                    }
                </div>
            </div>
        `;
        
        cartSummary.style.display = 'block';
        cartSummary.innerHTML = `
            ${loyaltyHTML}
            <div class="summary-row">
                <span>Subtotal:</span>
                <span>€${totals.subtotal.toFixed(2)}</span>
            </div>
            ${totals.loyaltyDiscount > 0 ? `
                <div class="summary-row discount">
                    <span>🎁 Loyalty Reward:</span>
                    <span>-€${totals.loyaltyDiscount.toFixed(2)}</span>
                </div>
            ` : ''}
            ${GLOBAL_PROMO.enabled ? `
                <div class="summary-row discount">
                    <span>${GLOBAL_PROMO.label}:</span>
                    <span>-€${totals.promoDiscount.toFixed(2)}</span>
                </div>
            ` : ''}
            ${appliedCoupon ? `
                <div class="summary-row discount">
                    <span>Coupon (${appliedCoupon.discount_percent}%):</span>
                    <span>-€${totals.couponDiscount.toFixed(2)}</span>
                </div>
            ` : ''}
            <div class="summary-row total">
                <span>Total:</span>
                <span>€${totals.total.toFixed(2)}</span>
            </div>
        `;
    }
}

function toggleCart() {
    const cartModal = document.getElementById('cartModal');
    cartModal.classList.toggle('active');
}

async function applyCoupon() {
    const couponInput = document.getElementById('couponInput');
    const couponCode = couponInput.value.trim().toUpperCase();
    
    if (!couponCode) {
        showNotification('❌ Please enter a coupon code', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/shop/validate-coupon', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ code: couponCode })
        });
        
        const data = await response.json();
        
        if (data.valid) {
            appliedCoupon = {
                code: couponCode,
                discount_percent: data.discount_percent
            };
            
            updateCartDisplay();
            showNotification(`✅ Coupon applied! ${data.discount_percent}% off`, 'success');
            couponInput.value = '';
            
            couponInput.disabled = true;
            document.querySelector('.apply-coupon-btn').textContent = '✓ Applied';
            document.querySelector('.apply-coupon-btn').disabled = true;
        } else {
            showNotification(`❌ ${data.message}`, 'error');
        }
    } catch (error) {
        showNotification('❌ Failed to validate coupon', 'error');
    }
}

function removeCoupon() {
    appliedCoupon = null;
    updateCartDisplay();
    document.getElementById('couponInput').disabled = false;
    document.getElementById('couponInput').value = '';
    document.querySelector('.apply-coupon-btn').textContent = 'Apply';
    document.querySelector('.apply-coupon-btn').disabled = false;
    showNotification('🎫 Coupon removed', 'info');
}

function proceedToCheckout() {
    if (cart.length === 0) {
        showNotification('❌ Your cart is empty!', 'error');
        return;
    }
    
    toggleCart();
    document.getElementById('checkoutModal').classList.add('active');
}

function closeCheckout() {
    document.getElementById('checkoutModal').classList.remove('active');
    document.getElementById('username').value = '';
    document.getElementById('usernameConfirm').value = '';
    document.getElementById('message').value = '';
}

async function completePurchase() {
    const username = document.getElementById('username').value.trim();
    const usernameConfirm = document.getElementById('usernameConfirm').value.trim();
    const message = document.getElementById('message').value.trim();

    if (!username || !usernameConfirm) {
        showNotification('❌ Please enter your username in both fields', 'error');
        return;
    }

    if (username !== usernameConfirm) {
        showNotification('❌ Usernames do not match!', 'error');
        return;
    }

    const validateBtn = document.querySelector('.modal-button.primary');
    const originalText = validateBtn.textContent;
    
    validateBtn.disabled = true;
    validateBtn.textContent = '🔍 Validating username...';
    
    try {
        const validateResponse = await fetch('/api/shop/validate-username', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: username })
        });
        
        const validateData = await validateResponse.json();
        
        if (!validateData.valid) {
            validateBtn.disabled = false;
            validateBtn.textContent = originalText;
            showNotification(`❌ Username "${username}" not found on Wolvesville!`, 'error');
            return;
        }
                
        const exactUsername = validateData.username || username;
        
        showNotification('✅ Username verified!', 'success');
        
        await new Promise(resolve => setTimeout(resolve, 500));
        
    } catch (error) {
        validateBtn.disabled = false;
        validateBtn.textContent = originalText;
        showNotification('❌ Failed to validate username. Please try again.', 'error');
        console.error('Validation error:', error);
        return;
    }

    validateBtn.textContent = '💳 Processing payment...';
    
    const totals = calculateTotal();

    try {
        const response = await fetch('/api/shop/create-cart-order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                cart: cart,
                username: username,
                message: message,
                coupon: appliedCoupon,
                globalPromo: GLOBAL_PROMO.enabled ? GLOBAL_PROMO : null,
                total: totals.total,
                breakdown: {
                    subtotal: totals.subtotal,
                    loyaltyDiscount: totals.loyaltyDiscount,
                    promoDiscount: totals.promoDiscount,
                    couponDiscount: totals.couponDiscount
                }
            })
        });

        const data = await response.json();

        if (data.error) {
            validateBtn.disabled = false;
            validateBtn.textContent = originalText;
            showNotification('❌ ' + data.error, 'error');
            return;
        }

        if (data.approval_url) {
            window.location.href = data.approval_url;
        } else {
            validateBtn.disabled = false;
            validateBtn.textContent = originalText;
            showNotification('❌ Failed to initiate payment', 'error');
        }
    } catch (error) {
        validateBtn.disabled = false;
        validateBtn.textContent = originalText;
        console.error('Error:', error);
        showNotification('❌ An error occurred. Please try again.', 'error');
    }
}

function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Initialize page
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 Initializing shop...');
    
    // Fetch shop data from database
    await fetchShopData();
    
    // Render products
    renderProducts();
    updateCartDisplay();
    
    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            const category = tab.getAttribute('data-category');
            currentCategory = category;
            renderProducts(category);
        });
    });
});