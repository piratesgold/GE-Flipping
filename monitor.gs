// =============================================================================
// GE Flips — Google Apps Script Background Monitor
// Paste this into your Google Sheet: Extensions > Apps Script
// Then set up a Time-driven trigger to run monitorOSRS() every 5 minutes.
// =============================================================================

// --- CONFIGURATION ---
var DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1481343528318668981/6dM4xigkg6X6JjcO-q6ukyYsFshAhh7_tI1ksN7oJ1Hc1k4Wktd_GOlPPGzEWTzcnfbM";
var OWNER_EMAIL = ""; // Set this to your OWNER_EMAIL from Streamlit secrets
var USER_AGENT = "GE Flips Google Apps Script Monitor";
var API_URL = "https://prices.runescape.wiki/api/v1/osrs/latest";

// Cooldown thresholds
var SQUEEZE_THRESHOLD_PCT = 0.01;  // 1% spike
var SPREAD_MIN_GP = 5000;          // 5k GP spread to exit cooldown

// --- COLUMN MAPPING ---
// These must match your Google Sheet column order (1-indexed)
// Adjust if your sheet columns are in a different order
var COL = {
  USER_EMAIL: 1,
  ITEM_ID: 2,
  ITEM_NAME: 3,
  PRICE: 4,
  QUANTITY: 5,
  STATUS: 6,
  TIMESTAMP: 7,
  LAST_ALERT_PRICE: 8,
  LAST_KNOWN_HIGH: 9,
  COOLDOWN: 10,
  FILLED_NOTIFIED: 11
};

function monitorOSRS() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Sheet1");
  if (!sheet) {
    Logger.log("Sheet1 not found.");
    return;
  }
  
  var data = sheet.getDataRange().getValues();
  var headers = data[0];
  
  // Auto-detect column indices from header row
  var colMap = {};
  for (var h = 0; h < headers.length; h++) {
    var header = String(headers[h]).toLowerCase().trim();
    if (header === "user_email") colMap.userEmail = h;
    else if (header === "item_id") colMap.itemId = h;
    else if (header === "item_name") colMap.itemName = h;
    else if (header === "price") colMap.price = h;
    else if (header === "quantity") colMap.quantity = h;
    else if (header === "status") colMap.status = h;
    else if (header === "timestamp") colMap.timestamp = h;
    else if (header === "last_alert_price") colMap.lastAlertPrice = h;
    else if (header === "last_known_high") colMap.lastKnownHigh = h;
    else if (header === "cooldown") colMap.cooldown = h;
    else if (header === "filled_notified") colMap.filledNotified = h;
  }
  
  // Ensure state columns exist — add headers if missing
  var lastCol = headers.length;
  if (colMap.lastAlertPrice === undefined) {
    sheet.getRange(1, lastCol + 1).setValue("last_alert_price");
    colMap.lastAlertPrice = lastCol;
    lastCol++;
  }
  if (colMap.lastKnownHigh === undefined) {
    sheet.getRange(1, lastCol + 1).setValue("last_known_high");
    colMap.lastKnownHigh = lastCol;
    lastCol++;
  }
  if (colMap.cooldown === undefined) {
    sheet.getRange(1, lastCol + 1).setValue("cooldown");
    colMap.cooldown = lastCol;
    lastCol++;
  }
  if (colMap.filledNotified === undefined) {
    sheet.getRange(1, lastCol + 1).setValue("filled_notified");
    colMap.filledNotified = lastCol;
    lastCol++;
  }

  // Re-read data in case we just added columns
  data = sheet.getDataRange().getValues();
  
  // Fetch live prices from OSRS Wiki
  var pricesData = {};
  try {
    var response = UrlFetchApp.fetch(API_URL, {
      headers: { "User-Agent": USER_AGENT },
      muteHttpExceptions: true
    });
    var json = JSON.parse(response.getContentText());
    pricesData = json.data || {};
  } catch (e) {
    Logger.log("Failed to fetch OSRS Wiki API: " + e);
    return;
  }
  
  var alerts = [];
  var sheetUpdated = false;
  
  // Process each row (skip header row at index 0)
  for (var i = 1; i < data.length; i++) {
    var row = data[i];
    var userEmail = String(row[colMap.userEmail] || "").trim();
    
    // Only process rows for the owner
    if (OWNER_EMAIL && userEmail !== OWNER_EMAIL) continue;
    
    var status = String(row[colMap.status] || "").trim();
    var itemId = String(Math.floor(Number(row[colMap.itemId]) || 0));
    var itemName = String(row[colMap.itemName] || "");
    var orderPrice = Math.floor(Number(row[colMap.price]) || 0);
    var qty = Math.floor(Number(row[colMap.quantity]) || 0);
    
    if (itemId === "0" || !itemName) continue;
    
    // --- Handle "Owned" rows: filled notifications ---
    if (status === "Owned") {
      var filledFlag = String(row[colMap.filledNotified] || "").trim().toLowerCase();
      if (filledFlag !== "true") {
        alerts.push(
          "✅ **[FILLED] " + itemName + "** (" + qty + "x)\n" +
          "> Final price: `" + formatGP(orderPrice) + " GP`\n" +
          "> *Your order has been filled and recorded.*"
        );
        sheet.getRange(i + 1, colMap.filledNotified + 1).setValue("true");
        sheetUpdated = true;
      }
      continue;
    }
    
    // Only process active orders
    if (status !== "Buying" && status !== "Selling") continue;
    
    var lastAlert = parseNum(row[colMap.lastAlertPrice]);
    var lastKnownHigh = parseNum(row[colMap.lastKnownHigh]);
    var isCooldown = String(row[colMap.cooldown] || "").trim().toLowerCase() === "true";
    
    var liveItem = pricesData[itemId] || {};
    var currentLow = Math.floor(Number(liveItem.low) || 0);
    var currentHigh = Math.floor(Number(liveItem.high) || 0);
    
    // --- Cooldown / Squeeze Detection (Buy orders only) ---
    if (status === "Buying" && currentHigh > 0 && currentLow > 0) {
      var spread = currentHigh - currentLow;
      
      if (!isCooldown) {
        if (lastKnownHigh > 0) {
          var pctChange = (currentHigh - lastKnownHigh) / lastKnownHigh;
          if (pctChange > SQUEEZE_THRESHOLD_PCT && spread < SPREAD_MIN_GP) {
            isCooldown = true;
            sheet.getRange(i + 1, colMap.cooldown + 1).setValue("true");
            sheetUpdated = true;
          }
        }
      } else {
        // Check exit condition
        if (spread >= SPREAD_MIN_GP) {
          isCooldown = false;
          sheet.getRange(i + 1, colMap.cooldown + 1).setValue("");
          sheetUpdated = true;
        }
      }
      
      // Always track last_known_high
      if (currentHigh !== lastKnownHigh) {
        sheet.getRange(i + 1, colMap.lastKnownHigh + 1).setValue(currentHigh);
        sheetUpdated = true;
      }
    }
    
    // Skip price alerts if in cooldown
    if (isCooldown) continue;
    
    var msg = null;
    var marketPrice = 0;
    
    if (status === "Buying") {
      if (currentLow > 0) {
        if (currentLow > orderPrice) {
          // Outbid
          marketPrice = currentLow;
          if (marketPrice !== lastAlert) {
            var diff = currentLow - orderPrice;
            msg = "⚠️ **[OUTBID] " + itemName + "** (" + qty + "x)\n" +
                  "> Your Bid: `" + formatGP(orderPrice) + " GP`\n" +
                  "> Current Low: `" + formatGP(currentLow) + " GP`\n" +
                  "> *You are outbid by " + formatGP(diff) + " GP!*";
          }
        } else if (currentLow <= orderPrice) {
          // Likely filled
          marketPrice = currentLow;
          if (marketPrice !== lastAlert) {
            if (lastAlert === 0) {
              // First run — seed silently
              sheet.getRange(i + 1, colMap.lastAlertPrice + 1).setValue(marketPrice);
              sheetUpdated = true;
            } else {
              msg = "✅ **[LIKELY FILLED] " + itemName + "** (" + qty + "x)\n" +
                    "> Your Bid: `" + formatGP(orderPrice) + " GP`\n" +
                    "> Current Low: `" + formatGP(currentLow) + " GP`\n" +
                    "> *Your order is likely filled!*";
            }
          }
        }
      }
    } else if (status === "Selling") {
      if (currentHigh > 0) {
        if (currentHigh < orderPrice) {
          // Undercut
          marketPrice = currentHigh;
          if (marketPrice !== lastAlert) {
            var diff = orderPrice - currentHigh;
            msg = "⚠️ **[UNDERCUT] " + itemName + "** (" + qty + "x)\n" +
                  "> Your Ask: `" + formatGP(orderPrice) + " GP`\n" +
                  "> Current High: `" + formatGP(currentHigh) + " GP`\n" +
                  "> *You are undercut by " + formatGP(diff) + " GP!*";
          }
        } else if (currentHigh >= orderPrice) {
          // Likely sold
          marketPrice = currentHigh;
          if (marketPrice !== lastAlert) {
            if (lastAlert === 0) {
              sheet.getRange(i + 1, colMap.lastAlertPrice + 1).setValue(marketPrice);
              sheetUpdated = true;
            } else {
              msg = "✅ **[LIKELY SOLD] " + itemName + "** (" + qty + "x)\n" +
                    "> Your Ask: `" + formatGP(orderPrice) + " GP`\n" +
                    "> Current High: `" + formatGP(currentHigh) + " GP`\n" +
                    "> *Your set is likely sold!*";
            }
          }
        }
      }
    }
    
    if (msg) {
      alerts.push(msg);
      sheet.getRange(i + 1, colMap.lastAlertPrice + 1).setValue(marketPrice);
      sheetUpdated = true;
    }
  }
  
  // Send Discord webhook
  if (alerts.length > 0) {
    var payload = {
      content: "🔔 **GE Flips Alert**\n" + alerts.join("\n\n")
    };
    try {
      UrlFetchApp.fetch(DISCORD_WEBHOOK, {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });
      Logger.log("Sent " + alerts.length + " alerts to Discord.");
    } catch (e) {
      Logger.log("Discord webhook failed: " + e);
    }
  } else {
    Logger.log("No alerts. All quiet.");
  }
}

// --- Helper: parse a number safely from a cell ---
function parseNum(val) {
  if (val === null || val === undefined || val === "") return 0;
  var n = Number(val);
  return isNaN(n) ? 0 : Math.floor(n);
}

// --- Helper: format GP with commas ---
function formatGP(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// =============================================================================
// SETUP INSTRUCTIONS:
// 1. Open your Google Sheet
// 2. Go to Extensions > Apps Script
// 3. Delete any existing code and paste this entire script
// 4. Set your OWNER_EMAIL at the top (line 9) to match your Streamlit secrets
// 5. Click Save (💾)
// 6. Click Run > monitorOSRS to test (authorize when prompted)
// 7. Go to Triggers (⏰ clock icon on the left sidebar)
// 8. Click "+ Add Trigger"
//    - Function: monitorOSRS
//    - Event source: Time-driven
//    - Type: Minutes timer
//    - Interval: Every 5 minutes
// 9. Save. You're done! Alerts will fire automatically 24/7.
// =============================================================================
