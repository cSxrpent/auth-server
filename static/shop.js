// Global promo configuration - will be loaded from DB
let GLOBAL_PROMO = {
    enabled: false,
    discountPercent: 0,
    label: ""
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
    bundles: '📦',
    dailyskins: '🎨',
    skinsets: '👕'
};

// Permanent base shop items (always available)
const BASE_SHOP_ITEMS = [
    { type: 'GOLDV2_1', cost: 450, price: 2.99, name: 'Gold Pack S', category: 'coins', goldReward: 600 },
    { type: 'GOLDV2_2', cost: 3400, price: 19.99, name: 'Gold Pack M', category: 'coins', goldReward: 5000 },
    { type: 'GOLDV2_3', cost: 9000, price: 49.99, name: 'Gold Pack L', category: 'coins', goldReward: 15000 },
    { type: 'BATTLE_PASS_COINS_1', cost: 160, price: 0.99, name: 'BP Coins S', category: 'bpcoins', battlePassCoinCount: 340 },
    { type: 'BATTLE_PASS_COINS_2', cost: 300, price: 1.99, name: 'BP Coins M', category: 'bpcoins', battlePassCoinCount: 720 },
    { type: 'BATTLE_PASS_COINS_3', cost: 590, price: 3.99, name: 'BP Coins L', category: 'bpcoins', battlePassCoinCount: 1480 },
    { type: 'EMOJI_1', cost: 520, price: 3.49, name: 'Emoji Pack 1', category: 'emote' },
    { type: 'EMOJI_2', cost: 520, price: 3.49, name: 'Emoji Pack 2', category: 'emote' },
    { type: 'EMOJI_3', cost: 520, price: 3.49, name: 'Emoji Pack 3', category: 'emote' },
    { type: 'BATTLE_PASS', cost: 620, price: 3.99, name: 'Battle Pass', category: 'premium' },
    { type: 'BATTLE_PASS_BUNDLE', cost: 1280, price: 7.99, name: 'Battle Pass Bundle', category: 'premium', isBestValue: true },
    { type: 'LOOT_BOX_1', cost: 320, price: 1.99, name: 'Loot Box x3', category: 'lootbox', lootBoxCount: 3 },
    { type: 'LOOT_BOX_2', cost: 2600, price: 15.99, name: 'Loot Box x30', category: 'lootbox', lootBoxCount: 30 },
    { type: 'LOOT_BOX_3', cost: 7400, price: 44.99, name: 'Loot Box x100', category: 'lootbox', lootBoxCount: 100, isBestValue: true },
    { type: 'CUSTOM_GAMES', cost: 680, price: 4.49, name: 'Custom Games', category: 'premium' },
    { type: 'CUSTOM_GAMES_PREMIUM', cost: 3100, price: 19.99, name: 'Custom Games Premium', category: 'premium' },
    { type: 'AUTO_DOUBLE_XP', cost: 3100, price: 19.99, name: 'Auto Double XP', category: 'premium' },
    { type: 'TALISMANS_PREMIUM', cost: 3100, price: 19.99, name: 'Talismans Premium', category: 'premium' },
    { type: 'ROLE_CARDS_1', cost: 85, price: 0.49, name: 'Role Card x1', category: 'rolecards', roleCardCount: 1 },
    { type: 'ROLE_CARDS_2', cost: 750, price: 4.49, name: 'Role Cards x10', category: 'rolecards', roleCardCount: 10 },
    { type: 'ROLE_CARDS_MONTHLY_BUNDLE', cost: 1250, price: 7.99, name: 'Role Cards Monthly', category: 'rolecards', minLoyaltyTokenCount: 5, isBestValue: true }
];


let currentCategory = 'all';
let selectedProduct = null;
let cart = [];
let appliedCoupon = null;
let shopData = null; // Store fetched shop data

// Load shop settings on page load
async function loadShopSettings() {
    try {
        const response = await fetch('/api/shop/settings');
        const settings = await response.json();
        GLOBAL_PROMO = {
            enabled: settings.global_promo_enabled,
            discountPercent: settings.global_promo_percent,
            label: settings.global_promo_label || ""
        };
        console.log('✅ Shop settings loaded:', GLOBAL_PROMO);
        
        // Update promo banner based on settings
        const banner = document.getElementById('promoBanner');
        if (GLOBAL_PROMO.enabled && GLOBAL_PROMO.label) {
            banner.style.display = 'block';
            const bannerText = document.getElementById('promoBannerText');
            if (bannerText) bannerText.textContent = GLOBAL_PROMO.label;
        } else {
            banner.style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to load shop settings:', error);
    }
}

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
    if (!shopData) return BASE_SHOP_ITEMS; // Return base items if no data yet
    
    const products = [...BASE_SHOP_ITEMS]; // Start with base items
    
    // Add bundles from database
    if (shopData.bundles) {
        shopData.bundles.forEach(bundle => {
            if (!bundle.image) {
                products.push({
                    ...bundle,
                    category: 'bundles',
                    imageUrl: null,
                    cost: bundle.cost || 0  // Ensure cost field exists
                });
                return;
            }
            
            // Extract base name from bundle type (e.g., BUNDLE_MONSTER -> monster)
            const baseName = bundle.type.replace('BUNDLE_', '').toLowerCase();
            
            // Try FOUR different URL formats:
            // 1. bundle-name.jpg (e.g., bundle-monster.jpg)
            // 2. nameBundle.jpg (e.g., musicBundle.jpg)
            // 3. bundle_name.jpg with underscores (e.g., bundle_once_upon_a_time.jpg)
            // 4. name.jpg (e.g., poolpartyrose.jpg)
            const bundleNameDash = `bundle-${baseName.replace(/_/g, '-')}`;
            const bundleNameCamel = baseName.replace(/_/g, '') + 'bundle';
            const bundleNameUnderscore = `bundle_${baseName}`;
            const bundleNamePlain = baseName.replace(/_/g, '');
            
            products.push({
                ...bundle,
                category: 'bundles',
                imageUrls: [
                    `https://cdn2.wolvesville.com/promos/${bundleNameDash}.jpg`,
                    `https://cdn2.wolvesville.com/promos/${bundleNameCamel}.jpg`,
                    `https://cdn2.wolvesville.com/promos/${bundleNameUnderscore}.jpg`,
                    `https://cdn2.wolvesville.com/promos/${bundleNamePlain}.jpg`
                ],
                cost: bundle.cost || 0  // Ensure cost field exists
            });
        });
    }
    
    // Add skin sets
    if (shopData.skin_sets) {
        shopData.skin_sets.forEach(skinSet => {
            // Extract the skin set name from type (e.g., GUDNITE_OUTFITS -> gudnite_outfits_promotion)
            const skinSetName = skinSet.type.toLowerCase().replace('_outfits', '_outfits_promotion');
            
            products.push({
                ...skinSet,
                category: 'skinsets',
                name: skinSet.name,
                imageUrl: `https://www.wolvesville.com/static/media/${skinSetName}.png`,
                cost: skinSet.cost || 0  // Ensure cost field exists
            });
        });
    }
    
    // Add daily skins
    if (shopData.daily_skins) {
        shopData.daily_skins.forEach(skin => {
            products.push({
                ...skin,
                category: 'dailyskins',
                name: skin.name,
                imageUrl: skin.imageName ? `https://cdn2.wolvesville.com/promos/${skin.imageName}@2x.jpg` : null,
                cost: skin.cost || 0  // Ensure cost field exists
            });
        });
    }
    
    // Add calendars with ICON images
    if (shopData.calendars) {
        shopData.calendars.forEach(cal => {
            products.push({
                type: 'CALENDAR',
                id: cal.id,
                name: cal.title,
                price: cal.price,
                cost: cal.cost,
                category: 'calendar',
                imageUrl: cal.iconName ? `https://cdn2.wolvesville.com/calendars/${cal.iconName}@2x.png` : null
            });
        });
    }
    
    return products;
}

// ============ SEARCH & FILTER ============
function searchAndFilterProducts() {
    const searchQuery = document.getElementById('searchInput')?.value.toLowerCase() || '';
    const category = currentCategory || 'all';
    
    const allProducts = getAllProducts();
    
    // Filter by category first
    let filtered = category === 'all' 
        ? allProducts 
        : allProducts.filter(p => p.category === category);
    
    // Then filter by search query
    if (searchQuery) {
        filtered = filtered.filter(p => 
            p.name.toLowerCase().includes(searchQuery) ||
            (p.type && p.type.toLowerCase().includes(searchQuery))
        );
    }
    
    return filtered;
}

// ============ GIFT CARDS ============
let giftCardBalance = 0;
let appliedGiftCode = null;
let checkedGiftCode = null;

// Gift Card Choice Modal
function showGiftCardChoiceModal() {
    document.getElementById('giftCardChoiceModal').style.display = 'flex';
}

function closeGiftCardChoiceModal() {
    document.getElementById('giftCardChoiceModal').style.display = 'none';
}

// Buy Gift Card Page
function showBuyGiftCardPage() {
    closeGiftCardChoiceModal();
    document.getElementById('buyGiftCardModal').style.display = 'flex';
    document.getElementById('customGiftAmount').value = '';
}

function closeBuyGiftCardModal() {
    document.getElementById('buyGiftCardModal').style.display = 'none';
    showGiftCardChoiceModal();
}

function addGiftCardToCart(amount) {
    let finalAmount = amount;
    
    if (!finalAmount) {
        finalAmount = parseFloat(document.getElementById('customGiftAmount').value);
    }
    
    if (!finalAmount || finalAmount <= 0) {
        showNotification('❌ Please enter a valid amount', 'error');
        return;
    }
    
    // Add gift card to cart
    cart.push({
        type: 'GIFT_CARD',
        name: `🎁 Gift Card €${finalAmount.toFixed(2)}`,
        price: finalAmount,
        quantity: 1,
        category: 'gift_card',
        giftCardAmount: finalAmount
    });
    
    showNotification(`✅ Gift Card €${finalAmount.toFixed(2)} added to cart!`, 'success');
    document.getElementById('buyGiftCardModal').style.display = 'none';
    updateCartDisplay();
    
    // Auto-open cart
    setTimeout(() => {
        toggleCart();
    }, 500);
}

// Redeem Gift Card Page
function showRedeemGiftCardPage() {
    closeGiftCardChoiceModal();
    document.getElementById('redeemGiftCardModal').style.display = 'flex';
    document.getElementById('redeemCode').value = '';
    document.getElementById('redeemStatus').innerHTML = '';
    document.getElementById('giftCardDetails').style.display = 'none';
}

function closeRedeemGiftCardModal() {
    document.getElementById('redeemGiftCardModal').style.display = 'none';
    showGiftCardChoiceModal();
}

async function checkGiftCardCode() {
    const code = document.getElementById('redeemCode').value.trim().toUpperCase();
    
    if (!code) {
        showNotification('❌ Please enter a gift card code', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/gift-codes/check', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ code })
        });
        
        const data = await response.json();
        
        if (data.valid) {
            checkedGiftCode = code;
            giftCardBalance = data.balance;
            document.getElementById('giftCardBalance').textContent = data.balance.toFixed(2);
            document.getElementById('giftCardDetails').style.display = 'block';
            document.getElementById('redeemStatus').innerHTML = `<div style="padding: 12px; background: rgba(46,213,115,0.2); border-radius: 8px; color: var(--success); border: 1px solid var(--success);">✅ Valid gift card found!</div>`;
            showNotification('✅ Gift card is valid!', 'success');
        } else {
            document.getElementById('giftCardDetails').style.display = 'none';
            document.getElementById('redeemStatus').innerHTML = `<div style="padding: 12px; background: rgba(255,71,87,0.2); border-radius: 8px; color: var(--danger); border: 1px solid var(--danger);">❌ ${data.message}</div>`;
            showNotification('❌ ' + data.message, 'error');
        }
    } catch (error) {
        console.error('Error checking gift code:', error);
        showNotification('❌ Error checking gift code', 'error');
    }
}

function applyRedeemGiftCard() {
    if (!checkedGiftCode) {
        showNotification('❌ Please check a gift card first', 'error');
        return;
    }
    
    appliedGiftCode = checkedGiftCode;
    giftCardBalance = parseFloat(document.getElementById('giftCardBalance').textContent);
    
    showNotification(`✅ Gift card applied! Balance: €${giftCardBalance.toFixed(2)}`, 'success');
    document.getElementById('redeemGiftCardModal').style.display = 'none';
    
    // Auto-open cart to show options
    setTimeout(() => {
        toggleCart();
    }, 500);
}



function showTopUpModal() {
    const totals = calculateTotal();
    const amountNeeded = Math.max(0, totals.total - giftCardBalance);
    
    document.getElementById('currentGiftBalance').textContent = giftCardBalance.toFixed(2);
    document.getElementById('amountNeeded').textContent = amountNeeded.toFixed(2);
    
    // Set top-up amount to the amount needed + 5 for buffer
    const suggestedTopUp = Math.ceil(amountNeeded / 5) * 5; // Round up to nearest €5
    document.getElementById('topUpAmount').value = Math.min(suggestedTopUp, 50);
    
    document.getElementById('topUpModal').style.display = 'flex';
}

function closeTopUpModal() {
    document.getElementById('topUpModal').style.display = 'none';
}

async function processTopUpPayment() {
    const topUpAmount = parseFloat(document.getElementById('topUpAmount').value);
    
    if (!topUpAmount || topUpAmount <= 0) {
        showNotification('❌ Please select a valid top-up amount', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/gift-cards/top-up', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                amount: topUpAmount,
                giftCode: appliedGiftCode
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showNotification('❌ ' + data.error, 'error');
            return;
        }
        
        if (data.approval_url) {
            // Redirect to PayPal to complete top-up
            window.location.href = data.approval_url;
        } else {
            showNotification('❌ Failed to create payment', 'error');
        }
    } catch (error) {
        console.error('Error creating top-up payment:', error);
        showNotification('❌ Error processing top-up', 'error');
    }
}

function renderProducts(category = 'all') {
    const productsContainer = document.getElementById('products');
    if (!productsContainer) return;
    
    currentCategory = category;
    
    // Use search and filter
    const filtered = searchAndFilterProducts();

    if (filtered.length === 0) {
        productsContainer.innerHTML = `
            <div class="empty-state">
                <div class="icon">🔍</div>
                <div>No products found</div>
            </div>
        `;
        return;
    }

    productsContainer.innerHTML = filtered.map(product => {
        // Best value badge
        let badgeHTML = '';
        if (product.isBestValue) {
            badgeHTML = '<div style="position:absolute;top:8px;right:8px;background:linear-gradient(135deg,var(--gold),#ffa500);color:#000;padding:4px 10px;border-radius:16px;font-weight:700;font-size:0.7rem;box-shadow:0 3px 12px rgba(255,215,0,0.4);z-index:2">🔥 BEST</div>';
        }
        
        // New badge
        if (product.isNew) {
            badgeHTML += '<div style="position:absolute;top:8px;left:8px;background:linear-gradient(135deg,#ff6b6b,#ee5a6f);color:#fff;padding:4px 10px;border-radius:16px;font-weight:700;font-size:0.7rem;box-shadow:0 3px 12px rgba(255,107,107,0.4);z-index:2">🆕 NEW</div>';
        }
        
        // Image display with proper sizing and fallback handling
        let imageHTML;
        
        if (product.imageUrls && product.imageUrls.length > 0) {
            // Multiple URL fallbacks (for bundles)
            const fallbackUrls = product.imageUrls.slice(1).map(url => `'${url}'`).join(',');
            imageHTML = `<div style="width:100%;height:140px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;overflow:hidden;border-radius:8px;">
                <img src="${product.imageUrls[0]}" alt="${product.name}" 
                     style="max-width:100%;max-height:100%;object-fit:contain;" 
                     onerror="tryNextImage(this, [${fallbackUrls}])">
            </div>`;
        } else if (product.imageUrl) {
            // Single URL (for other items)
            imageHTML = `<div style="width:100%;height:140px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;overflow:hidden;border-radius:8px;">
                <img src="${product.imageUrl}" alt="${product.name}" 
                     style="max-width:100%;max-height:100%;object-fit:contain;" 
                     onerror="this.parentElement.style.display='none'">
            </div>`;
        } else {
            // No image - show emoji
            imageHTML = `<div class="category-emoji" style="font-size:3rem;margin:20px 0">${CATEGORY_EMOJIS[product.category] || '📦'}</div>`;
        }
        
        return `
            <div class="product-card" style="position:relative;display:flex;flex-direction:column;min-height:280px;padding:20px">
                ${badgeHTML}
                ${imageHTML}
                <div style="flex:1;display:flex;flex-direction:column;justify-content:space-between;text-align:center">
                    <div>
                        <div class="product-name" style="margin-bottom:12px;font-size:1.1rem;font-weight:700">${product.name || product.title}</div>
                        ${product.goldReward ? `<div style="color:var(--gold);font-size:0.9rem;margin-bottom:6px;font-weight:600">+${product.goldReward.toLocaleString()} Gold</div>` : ''}
                        ${product.battlePassCoinCount ? `<div style="color:#7b4bff;font-size:0.9rem;margin-bottom:6px;font-weight:600">+${product.battlePassCoinCount.toLocaleString()} BP Coins</div>` : ''}
                        ${product.lootBoxCount ? `<div style="color:var(--accent);font-size:0.9rem;margin-bottom:6px;font-weight:600">${product.lootBoxCount}x Loot Boxes</div>` : ''}
                        ${product.roleCardCount ? `<div style="color:#ff6b9d;font-size:0.9rem;margin-bottom:6px;font-weight:600">${product.roleCardCount}x Role Cards</div>` : ''}
                    </div>
                    <div style="margin-top:auto;width:100%">
                        <div class="product-price" style="margin-bottom:12px;font-size:1.5rem;font-weight:700">€${product.price.toFixed(2)}</div>

                        <button class="buy-button" style="width:100%;padding:14px;font-size:1rem;font-weight:600;border-radius:12px" onclick='addToCart(${JSON.stringify(product).replace(/'/g, "&apos;")})'>
                            🛒 Add to Cart
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}


function tryNextImage(img, fallbackUrls) {
    if (fallbackUrls.length > 0) {
        const nextUrl = fallbackUrls.shift();
        img.onerror = () => tryNextImage(img, fallbackUrls);
        img.src = nextUrl;
    } else {
        // All URLs failed - hide image container
        img.parentElement.style.display = 'none';
    }
}

function addToCart(product) {
    // Categories that can only be purchased once (no quantity increase)
    const singlePurchaseCategories = ['bundles', 'calendar', 'dailyskins', 'skinsets', 'premium', 'emote', 'gift_card'];
    
    const existingIndex = cart.findIndex(item => 
        item.type === product.type || 
        (item.id && item.id === product.id)
    );
    
    if (existingIndex >= 0) {
        // Check if this is a single-purchase item
        if (singlePurchaseCategories.includes(product.category)) {
            showNotification('⚠️ This item is already in your cart!', 'info');
            return;
        }
        
        // Allow quantity increase for other items (coins, loot boxes, etc.)
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
                    ${['bundles', 'calendar', 'dailyskins', 'skinsets', 'premium', 'emote', 'gift_card'].includes(item.category) ? 
                        // Single-purchase items: only show remove button
                        `<button onclick="removeFromCart(${index})" class="remove-btn">🗑️</button>` :
                        // Multi-purchase items: show quantity controls
                        `<button onclick="updateCartQuantity(${index}, -1)" class="qty-btn">−</button>
                        <span class="cart-item-qty">${item.quantity}</span>
                        <button onclick="updateCartQuantity(${index}, 1)" class="qty-btn">+</button>
                        <button onclick="removeFromCart(${index})" class="remove-btn">🗑️</button>`
                    }
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

    // Calculate final payment amount after gift card balance
    let finalPaymentAmount = totals.total;
    let giftCardUsed = 0;
    
    if (giftCardBalance > 0 && appliedGiftCode) {
        giftCardUsed = Math.min(giftCardBalance, totals.total);
        finalPaymentAmount = totals.total - giftCardUsed;
    }

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
                giftCard: appliedGiftCode ? {
                    code: appliedGiftCode,
                    balance: giftCardBalance,
                    used: giftCardUsed
                } : null,
                finalPaymentAmount: finalPaymentAmount,
                breakdown: {
                    subtotal: totals.subtotal,
                    loyaltyDiscount: totals.loyaltyDiscount,
                    promoDiscount: totals.promoDiscount,
                    couponDiscount: totals.couponDiscount,
                    giftCardDiscount: giftCardUsed
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

        // Check if payment is needed
        if (finalPaymentAmount <= 0) {
            // Full payment covered by gift card - backend already processed everything
            showNotification('✅ Purchase completed with gift card!', 'success');
            // Wait a moment for session to be set, then redirect to success page
            setTimeout(() => {
                if (data.redirect) {
                    window.location.href = data.redirect;
                } else {
                    window.location.href = '/cart/success';
                }
            }, 1000);
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
    
    // Load shop settings (promo banner, etc)
    await loadShopSettings();
    
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