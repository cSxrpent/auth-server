const ITEMS = [
    // GOLD
    { type: "GOLDV2_1", cost: 450, category: "coins", price: 2.99, name: "Gold Package 1" },
    { type: "GOLDV2_2", cost: 3400, category: "coins", price: 19.99, name: "Gold Package 2" },
    { type: "GOLDV2_3", cost: 9000, category: "coins", price: 49.99, name: "Gold Package 3" },

    // BATTLE PASS COINS
    { type: "BATTLE_PASS_COINS_1", cost: 160, category: "bpcoins", price: 1.49, name: "BP Coins Pack 1" },
    { type: "BATTLE_PASS_COINS_2", cost: 300, category: "bpcoins", price: 2.49, name: "BP Coins Pack 2" },
    { type: "BATTLE_PASS_COINS_3", cost: 590, category: "bpcoins", price: 3.99, name: "BP Coins Pack 3" },

    // EMOTES
    { type: "EMOJI_1", cost: 520, category: "emote", price: 3.49, name: "Emoji Pack 1" },
    { type: "EMOJI_2", cost: 520, category: "emote", price: 3.49, name: "Emoji Pack 2" },
    { type: "EMOJI_3", cost: 520, category: "emote", price: 3.49, name: "Emoji Pack 3" },

    // PREMIUM
    { type: "BATTLE_PASS", cost: 620, category: "premium", price: 4.49, name: "Battle Pass" },
    { type: "BATTLE_PASS_BUNDLE", cost: 1280, category: "premium", price: 8.99, name: "Battle Pass Bundle" },
    { type: "CUSTOM_GAMES_PREMIUM", cost: 3100, category: "premium", price: 19.99, name: "Custom Games Premium" },
    { type: "PROFILE_CUSTOMIZATION", cost: 3100, category: "premium", price: 19.99, name: "Profile Customization" },
    { type: "AUTO_DOUBLE_XP", cost: 3100, category: "premium", price: 17.99, name: "Auto Double XP" },
    { type: "TALISMANS_PREMIUM", cost: 3100, category: "premium", price: 19.99, name: "Talismans Premium" },

    // LOOT BOXES
    { type: "LOOT_BOX_1", cost: 320, category: "lootbox", price: 2.49, name: "Loot Box Small" },
    { type: "LOOT_BOX_2", cost: 2600, category: "lootbox", price: 16.99, name: "Loot Box Medium" },
    { type: "LOOT_BOX_3", cost: 7400, category: "lootbox", price: 44.99, name: "Loot Box Large" },

    // ROLE CARDS
    { type: "ROLE_CARDS_1", cost: 85, category: "rolecards", price: 0.99, name: "Role Cards Pack 1" },
    { type: "ROLE_CARDS_2", cost: 750, category: "rolecards", price: 4.99, name: "Role Cards Pack 2" },
    { type: "ROLE_CARDS_MONTHLY_BUNDLE", cost: 1250, category: "rolecards", price: 7.99, name: "Role Cards Monthly Bundle" }
];

const CALENDARS = [
    { id: "calendar-howl-2021", cost: 600, title: "Time to howl!", price: 3.99 },
    { id: "calendar-future-2021", cost: 600, title: "Future calendar", price: 3.99 },
    { id: "calendar-wintertime-2021", cost: 600, title: "Winter calendar", price: 3.99 },
    { id: "calendar-january-2022", cost: 600, title: "Tiger calendar", price: 3.99 },
    { id: "calendar-valentine-2022", cost: 600, title: "Valentine's calendar", price: 3.99 },
    { id: "calendar-4thbirthday-2022", cost: 600, title: "Birthday calendar", price: 3.99 },
    { id: "calendar-aliens-2021", cost: 600, title: "Galaxy calendar", price: 3.99 },
    { id: "calendar-baby-animals-2021", cost: 600, title: "Baby animals calendar", price: 3.99 },
    { id: "calendar-secret-cult-2021", cost: 600, title: "Secret cult calendar", price: 3.99 },
    { id: "calendar-greenmonth-2022", cost: 600, title: "Green month calendar", price: 3.99 },
    { id: "calendar-summer-2022", cost: 600, title: "Summer calendar", price: 3.99 },
    { id: "calendar-bakery-2022", cost: 600, title: "Bakery calendar", price: 3.99 },
    { id: "calendar-darkgalaxy-2022", cost: 600, title: "Dark galaxy calendar", price: 3.99 },
    { id: "calendar-red-2022", cost: 600, title: "Red calendar", price: 3.99 },
    { id: "calendar-fallingautumn-2022", cost: 600, title: "Autumn calendar", price: 3.99 },
    { id: "calendar-hell-2022", cost: 600, title: "Hell calendar", price: 3.99 },
    { id: "calendar-funkynight-2022", cost: 600, title: "Funky nights calendar", price: 3.99 },
    { id: "calendar-xmas2022-2022", cost: 600, title: "Advent calendar", price: 3.99 },
    { id: "calendar-newmeow-2022", cost: 600, title: "Meow calendar", price: 3.99 },
    { id: "calendar-minival23-2022", cost: 600, title: "Valentine calendar", price: 3.99 },
    { id: "calendar-5thbirthday-2023", cost: 600, title: "Birthday calendar", price: 3.99 },
    { id: "calendar-eggventure-2025", cost: 600, title: "Eggventure calendar", price: 3.99 },
    { id: "calendar-newyear-2026", cost: 600, title: "New year 2026 calendar", price: 3.99 }
];

const BUNDLES = [
    { type: "BUNDLE_ANGELXMAS", cost: 450, price: 2.99, name: "Angel Xmas Bundle", image: "bundle-angelxmas" },
    { type: "BUNDLE_BLACKFIREDAY", cost: 450, price: 2.99, name: "Black Fire Day Bundle", image: "bundle-blackfireday" },
    { type: "BUNDLE_BDAY_24", cost: 450, price: 2.99, name: "Birthday 24 Bundle", image: "bundle-bday-24" },
    { type: "BUNDLE_BIRTHDAYCAKE", cost: 450, price: 2.99, name: "Birthday Cake Bundle", image: "bundle-birthdaycake" },
    { type: "BUNDLE_BLACKFRIDAYWOLF", cost: 450, price: 2.99, name: "Black Friday Wolf Bundle", image: "bundle-blackfridaywolf" },
    { type: "BUNDLE_NEWYEAR25", cost: 450, price: 2.99, name: "New Year 2025 Bundle", image: "bundle-newyear25" },
    { type: "BUNDLE_ROYALXMAS", cost: 450, price: 2.99, name: "Royal Xmas Bundle", image: "bundle-royalxmas" },
    { type: "BUNDLE_ALITTLEMATCHWOLF", cost: 450, price: 2.99, name: "A Little Match Wolf Bundle", image: "bundle-alittlematchwolf" },
    { type: "BUNDLE_DRAWOLF", cost: 450, price: 2.99, name: "Drawolf Bundle", image: "bundle-drawolf" },
    { type: "BUNDLE_SLEEPINBUNNY", cost: 450, price: 2.99, name: "Sleepin Bunny Bundle", image: "bundle-sleepinbunny" },
    { type: "BUNDLE_PIGKABOO", cost: 450, price: 2.99, name: "Pigkaboo Bundle", image: "bundle-pigkaboo" },
    { type: "BUNDLE_POOLPARTYROSE", cost: 450, price: 2.99, name: "Pool Party Rose Bundle", image: "bundle-poolpartyrose" },
    { type: "BUNDLE_PROUDTOBEME", cost: 450, price: 2.99, name: "Proud To Be Me Bundle", image: "bundle-proudtobeme" },
    { type: "BUNDLE_ROLE_ICONS_EASTER", cost: 450, price: 2.99, name: "Easter Role Icons Bundle", image: "bundle-role-icons-easter" },
    { type: "BUNDLE_ROLE_ICONS_EASTER_2024", cost: 450, price: 2.99, name: "Easter 2024 Role Icons Bundle", image: "bundle-role-icons-easter-2024" },
    { type: "BUNDLE_CHOCOLATEBOX", cost: 450, price: 2.99, name: "Chocolate Box Bundle", image: "bundle-chocolatebox" },
    { type: "BUNDLE_SQUID", cost: 450, price: 2.99, name: "Squid Bundle", image: "bundle-squid" },
    { type: "BUNDLE_DARK_CUPID", cost: 800, price: 4.99, name: "Dark Cupid Bundle", image: "bundle-dark-cupid" },
    { type: "BUNDLE_EASTER_24", cost: 800, price: 4.99, name: "Easter 24 Bundle", image: "bundle-easter-24" },
    { type: "BUNDLE_WATERMELON", cost: 800, price: 4.99, name: "Watermelon Bundle", image: "bundle-watermelon" },
    { type: "BUNDLE_BALLGAME", cost: 800, price: 4.99, name: "Ball Game Bundle", image: "bundle-ballgame" },
    { type: "BUNDLE_BLOSSOM", cost: 800, price: 4.99, name: "Blossom Bundle", image: "bundle-blossom" },
    { type: "BUNDLE_MUSIC", cost: 800, price: 4.99, name: "Music Bundle", image: "bundle-music" },
    { type: "BUNDLE_ONCEUPONATIME", cost: 800, price: 4.99, name: "Once Upon A Time Bundle", image: "bundle-onceuponatime" },
    { type: "BUNDLE_GOTHIC", cost: 800, price: 4.99, name: "Gothic Bundle", image: "bundle-gothic" },
    { type: "BUNDLE_MONSTER", cost: 800, price: 4.99, name: "Monster Bundle", image: "bundle-monster" },
    { type: "BUNDLE_YOKAI", cost: 800, price: 4.99, name: "Yokai Bundle", image: "bundle-yokai" },
    { type: "BUNDLE_STRAWBERRY", cost: 800, price: 4.99, name: "Strawberry Bundle", image: "bundle-strawberry" },
    { type: "BUNDLE_OCEAN", cost: 800, price: 4.99, name: "Ocean Bundle", image: "bundle-ocean" },
    { type: "BUNDLE_BROWNIE", cost: 800, price: 4.99, name: "Brownie Bundle", image: "bundle-brownie" },
    { type: "BUNDLE_XMASTIME", cost: 800, price: 4.99, name: "Christmas Time Bundle", image: "bundle-xmastime" },
    { type: "BUNDLE_MUKBANG", cost: 800, price: 4.99, name: "Mukbang Bundle", image: "bundle-mukbang" },
    { type: "BUNDLE_SNAKE", cost: 800, price: 4.99, name: "Snake Bundle", image: "bundle-snake" },
    { type: "BUNDLE_MEOWCOFFEE", cost: 800, price: 4.99, name: "Meow Coffee Bundle", image: "bundle-meowcoffee" },
    { type: "BUNDLE_BUBBLEHEART", cost: 800, price: 4.99, name: "Bubble Heart Bundle", image: "bundle-bubbleheart" },
    { type: "BUNDLE_CRYSTAL", cost: 800, price: 4.99, name: "Crystal Bundle", image: "bundle-crystal" },
    { type: "BUNDLE_CARTOON", cost: 800, price: 4.99, name: "Cartoon Bundle", image: "bundle-cartoon" },
    { type: "BUNDLE_FLORIST", cost: 800, price: 4.99, name: "Florist Bundle", image: "bundle-florist" },
    { type: "BUNDLE_TRAVEL", cost: 800, price: 4.99, name: "Travel Bundle", image: "bundle-travel" },
    { type: "BUNDLE_SOLAR", cost: 800, price: 4.99, name: "Solar Bundle", image: "bundle-solar" },
    { type: "BUNDLE_ACADEMIC", cost: 800, price: 4.99, name: "Academic Bundle", image: "bundle-academic" },
    { type: "BUNDLE_CIRCUS", cost: 800, price: 4.99, name: "Circus Bundle", image: "bundle-circus" },
    { type: "BUNDLE_SCRAPPYDOLL", cost: 800, price: 4.99, name: "Scrappy Doll Bundle", image: "bundle-scrappydoll" },
    { type: "BUNDLE_TRIBAL", cost: 800, price: 4.99, name: "Tribal Bundle", image: "bundle-tribal" },
    { type: "BUNDLE_FLUFFY", cost: 800, price: 4.99, name: "Fluffy Bundle", image: "bundle-fluffy" },
    { type: "BUNDLE_FRUIT", cost: 800, price: 4.99, name: "Fruit Bundle", image: "bundle-fruit" },
    { type: "BUNDLE_DRAGON", cost: 800, price: 4.99, name: "Dragon Bundle", image: "bundle-dragon" },
    { type: "BUNDLE_AUTUMN", cost: 800, price: 4.99, name: "Autumn Bundle", image: "bundle-autumn" },
    { type: "BUNDLE_FAIRY", cost: 800, price: 4.99, name: "Fairy Bundle", image: "bundle-fairy" },
    { type: "BUNDLE_PUZZLE", cost: 800, price: 4.99, name: "Puzzle Bundle", image: "bundle-puzzle" },
    { type: "BUNDLE_BAW", cost: 800, price: 4.99, name: "Black And White Bundle", image: "bundle-baw" },
    { type: "BUNDLE_DARKKNIGHT", cost: 800, price: 4.99, name: "Dark Knight Bundle", image: "bundle-darkknight" },
    { type: "BUNDLE_BAB", cost: 800, price: 4.99, name: "BAB Bundle", image: "bundle-bab" },
    { type: "BUNDLE_CHROMEVOID", cost: 800, price: 4.99, name: "Chrome Void Bundle", image: "bundle-chromevoid" },
    { type: "BUNDLE_FROG", cost: 800, price: 4.99, name: "Frog Bundle", image: "bundle-frog" },
    { type: "BUNDLE_CHOCOMINT", cost: 800, price: 4.99, name: "Choco Mint Bundle", image: "bundle-chocomint" },
    { type: "BUNDLE_SUSHI", cost: 800, price: 4.99, name: "Sushi Bundle", image: "bundle-sushi" },
    { type: "BUNDLE_DARKNESS", cost: 800, price: 4.99, name: "Darkness Bundle", image: "bundle-darkness" },
    { type: "BUNDLE_ICECREAM", cost: 800, price: 4.99, name: "Ice Cream Bundle", image: "bundle-icecream" },
    { type: "BUNDLE_MYCAKE", cost: 800, price: 4.99, name: "My Cake Bundle", image: "bundle-mycake" },
    { type: "BUNDLE_CURSED", cost: 800, price: 4.99, name: "Cursed Bundle", image: "bundle-cursed" },
    { type: "BUNDLE_LEOPARD", cost: 800, price: 4.99, name: "Leopard Bundle", image: "bundle-leopard" },
    { type: "BUNDLE_YEEHAW", cost: 800, price: 4.99, name: "Yeehaw Bundle", image: "bundle-yeehaw" }
];


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

function getAllProducts() {
    const products = [...ITEMS];
    CALENDARS.forEach(cal => {
        products.push({
            type: 'CALENDAR',
            id: cal.id,
            name: cal.title,
            price: cal.price,
            cost: cal.cost,
            category: 'calendar'
        });
    });
    BUNDLES.forEach(bundle => {
        products.push({
            ...bundle,
            category: 'bundles'
        });
    });
    return products;
}

function renderProducts(category = 'all') {
    const productsContainer = document.getElementById('products');
    const allProducts = getAllProducts();
    const filtered = category === 'all' 
        ? allProducts 
        : allProducts.filter(p => p.category === category);

    productsContainer.innerHTML = filtered.map(product => `
        <div class="product-card">
            <div class="category-emoji">${CATEGORY_EMOJIS[product.category] || '📦'}</div>
            ${product.image ? `<img class="product-image" src="https://cdn2.wolvesville.com/promos/${product.image}@2x.jpg" alt="${product.name}">` : ''}
            <div class="product-name">${product.name || product.title}</div>
            <div class="product-price">€${product.price.toFixed(2)}</div>
            <button class="buy-button" onclick='addToCart(${JSON.stringify(product).replace(/'/g, "&apos;")})'>
                🛒 Add to Cart
            </button>
        </div>
    `).join('');
}

function addToCart(product) {
    // Check if product already in cart
    const existingIndex = cart.findIndex(item => item.type === product.type);
    
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
    const subtotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    let discount = 0;
    
    if (appliedCoupon) {
        discount = subtotal * (appliedCoupon.discount_percent / 100);
    }
    
    return {
        subtotal: subtotal,
        discount: discount,
        total: subtotal - discount
    };
}

function updateCartDisplay() {
    const cartBtn = document.getElementById('cartButton');
    const cartCount = document.getElementById('cartCount');
    const cartItems = document.getElementById('cartItems');
    const cartSummary = document.getElementById('cartSummary');
    
    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    
    // Update cart button
    if (totalItems > 0) {
        cartCount.textContent = totalItems;
        cartCount.style.display = 'flex';
    } else {
        cartCount.style.display = 'none';
    }
    
    // Update cart items
    if (cart.length === 0) {
        cartItems.innerHTML = '<div class="empty-cart">🛒 Your cart is empty</div>';
        cartSummary.style.display = 'none';
    } else {
        cartItems.innerHTML = cart.map((item, index) => `
            <div class="cart-item">
                <div class="cart-item-info">
                    <div class="cart-item-name">${item.name}</div>
                    <div class="cart-item-price">€${item.price.toFixed(2)}</div>
                </div>
                <div class="cart-item-controls">
                    <button onclick="updateCartQuantity(${index}, -1)" class="qty-btn">−</button>
                    <span class="cart-item-qty">${item.quantity}</span>
                    <button onclick="updateCartQuantity(${index}, 1)" class="qty-btn">+</button>
                    <button onclick="removeFromCart(${index})" class="remove-btn">🗑️</button>
                </div>
            </div>
        `).join('');
        
        const totals = calculateTotal();
        
        cartSummary.style.display = 'block';
        cartSummary.innerHTML = `
            <div class="summary-row">
                <span>Subtotal:</span>
                <span>€${totals.subtotal.toFixed(2)}</span>
            </div>
            ${appliedCoupon ? `
                <div class="summary-row discount">
                    <span>Discount (${appliedCoupon.discount_percent}%):</span>
                    <span>-€${totals.discount.toFixed(2)}</span>
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
            
            // Disable coupon input
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

    const totals = calculateTotal();

    try {
        // Create PayPal order for cart
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
                total: totals.total
            })
        });

        const data = await response.json();

        if (data.error) {
            showNotification('❌ ' + data.error, 'error');
            return;
        }

        if (data.approval_url) {
            // Redirect to PayPal
            window.location.href = data.approval_url;
        } else {
            showNotification('❌ Failed to initiate payment', 'error');
        }
    } catch (error) {
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
document.addEventListener('DOMContentLoaded', () => {
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