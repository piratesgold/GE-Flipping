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
    else if (header === "last_alert_type") colMap.lastAlertType = h;
  }
  
  // Ensure state columns exist — add headers if missing
  var lastCol = headers.length;
  var requiredCols = [
    {key: "lastAlertPrice", name: "last_alert_price"},
    {key: "lastKnownHigh", name: "last_known_high"},
    {key: "cooldown", name: "cooldown"},
    {key: "filledNotified", name: "filled_notified"},
    {key: "lastAlertType", name: "last_alert_type"}
  ];
  for (var c = 0; c < requiredCols.length; c++) {
    if (colMap[requiredCols[c].key] === undefined) {
      sheet.getRange(1, lastCol + 1).setValue(requiredCols[c].name);
      colMap[requiredCols[c].key] = lastCol;
      lastCol++;
    }
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
      if (filledFlag !== "true" && filledFlag !== "1.0" && filledFlag !== "1") {
        alerts.push(
          "✅ **[FILLED] " + itemName + "** (" + qty + "x)\n" +
          "> Final price: `" + formatGP(orderPrice) + " GP`\n" +
          "> *Your order has been filled and recorded.*"
        );
        sheet.getRange(i + 1, colMap.filledNotified + 1).setValue("true");
      }
      continue;
    }
    
    // Only process active orders (Buying / Selling)
    if (status !== "Buying" && status !== "Selling") continue;
    
    var lastAlert = parseNum(row[colMap.lastAlertPrice]);
    var lastKnownHigh = parseNum(row[colMap.lastKnownHigh]);
    var rawCooldown = String(row[colMap.cooldown] || "").trim().toLowerCase();
    var isCooldown = (rawCooldown === "true" || rawCooldown === "1.0" || rawCooldown === "1");
    var lastAlertType = String(row[colMap.lastAlertType] || "").trim().toLowerCase();
    
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
          }
        }
      } else {
        if (spread >= SPREAD_MIN_GP) {
          isCooldown = false;
          sheet.getRange(i + 1, colMap.cooldown + 1).setValue("");
        }
      }
      
      // Always track last_known_high
      if (currentHigh !== lastKnownHigh) {
        sheet.getRange(i + 1, colMap.lastKnownHigh + 1).setValue(currentHigh);
      }
    }
    
    // Skip price alerts if in cooldown
    if (isCooldown) continue;
    
    var msg = null;
    var marketPrice = 0;
    var alertType = "";
    
    // =========================================================================
    // BUYING LOGIC
    // =========================================================================
    if (status === "Buying") {
      if (currentLow > 0) {
        if (currentLow <= orderPrice) {
          // Price is at or below our bid → LIKELY FILLED
          marketPrice = currentLow;
          if (marketPrice !== lastAlert) {
            if (lastAlert === 0) {
              // First run for this order — seed silently, no alert
              sheet.getRange(i + 1, colMap.lastAlertPrice + 1).setValue(marketPrice);
              sheet.getRange(i + 1, colMap.lastAlertType + 1).setValue("seeded");
            } else {
              msg = "✅ **[LIKELY FILLED] " + itemName + "** (" + qty + "x)\n" +
                    "> Your Bid: `" + formatGP(orderPrice) + " GP`\n" +
                    "> Current Low: `" + formatGP(currentLow) + " GP`\n" +
                    "> *Your order is likely filled!*";
              alertType = "filled";
            }
          }
        } else if (currentLow > orderPrice) {
          // Price is above our bid
          // BUT: if the LAST alert we sent was "filled", the order probably already
          // completed. Don't send an OUTBID alert — that would be misleading.
          if (lastAlertType === "filled") {
            // Suppress outbid. The order likely filled at our price, and now
            // the market has moved on. Stay silent.
            Logger.log("Suppressing OUTBID for " + itemName + " — last alert was LIKELY FILLED.");
          } else {
            // Genuine outbid scenario
            marketPrice = currentLow;
            if (marketPrice !== lastAlert) {
              var diff = currentLow - orderPrice;
              msg = "⚠️ **[OUTBID] " + itemName + "** (" + qty + "x)\n" +
                    "> Your Bid: `" + formatGP(orderPrice) + " GP`\n" +
                    "> Current Low: `" + formatGP(currentLow) + " GP`\n" +
                    "> *You are outbid by " + formatGP(diff) + " GP!*";
              alertType = "outbid";
            }
          }
        }
      }
    }
    
    // =========================================================================
    // SELLING LOGIC
    // =========================================================================
    else if (status === "Selling") {
      if (currentHigh > 0) {
        if (currentHigh >= orderPrice) {
          // Price is at or above our ask → LIKELY SOLD
          marketPrice = currentHigh;
          if (marketPrice !== lastAlert) {
            if (lastAlert === 0) {
              sheet.getRange(i + 1, colMap.lastAlertPrice + 1).setValue(marketPrice);
              sheet.getRange(i + 1, colMap.lastAlertType + 1).setValue("seeded");
            } else {
              msg = "✅ **[LIKELY SOLD] " + itemName + "** (" + qty + "x)\n" +
                    "> Your Ask: `" + formatGP(orderPrice) + " GP`\n" +
                    "> Current High: `" + formatGP(currentHigh) + " GP`\n" +
                    "> *Your set is likely sold!*";
              alertType = "sold";
            }
          }
        } else if (currentHigh < orderPrice) {
          // Price is below our ask
          // BUT: if the LAST alert was "sold", the set probably already sold.
          // Don't send an UNDERCUT alert.
          if (lastAlertType === "sold") {
            Logger.log("Suppressing UNDERCUT for " + itemName + " — last alert was LIKELY SOLD.");
          } else {
            marketPrice = currentHigh;
            if (marketPrice !== lastAlert) {
              var diff = orderPrice - currentHigh;
              msg = "⚠️ **[UNDERCUT] " + itemName + "** (" + qty + "x)\n" +
                    "> Your Ask: `" + formatGP(orderPrice) + " GP`\n" +
                    "> Current High: `" + formatGP(currentHigh) + " GP`\n" +
                    "> *You are undercut by " + formatGP(diff) + " GP!*";
              alertType = "undercut";
            }
          }
        }
      }
    }
    
    // Write alert state back to the sheet
    if (msg) {
      alerts.push(msg);
      sheet.getRange(i + 1, colMap.lastAlertPrice + 1).setValue(marketPrice);
      sheet.getRange(i + 1, colMap.lastAlertType + 1).setValue(alertType);
    }
  }
  
  // Send Discord webhook
  if (alerts.length > 0) {
    var payloads = [];
    var currentPayload = "🔔 **GE Flips Alert**\n";
    
    for (var a = 0; a < alerts.length; a++) {
      // Keep well under 2000 char Discord max
      if (currentPayload.length + alerts[a].length > 1800) {
        payloads.push(currentPayload);
        currentPayload = "🔔 **GE Flips Alert (Cont.)**\n";
      }
      currentPayload += alerts[a] + "\n\n";
    }
    payloads.push(currentPayload);

    for (var p = 0; p < payloads.length; p++) {
      var payloadStr = JSON.stringify({ content: payloads[p] });
      var success = false;
      var retries = 3;
      var backoff = 1500;
      
      while (!success && retries > 0) {
        try {
          var res = UrlFetchApp.fetch(DISCORD_WEBHOOK, {
            method: "post",
            contentType: "application/json",
            payload: payloadStr,
            muteHttpExceptions: true
          });
          
          var code = res.getResponseCode();
          if (code === 429) {
            Logger.log("Discord rate limited. Retrying in " + backoff + "ms");
            Utilities.sleep(backoff);
            backoff *= 2;
            retries--;
          } else {
            success = true;
          }
        } catch (e) {
          Logger.log("Discord webhook failed: " + e);
          Utilities.sleep(backoff);
          backoff *= 2;
          retries--;
        }
      }
    }
    Logger.log("Processed " + alerts.length + " alerts via webhook.");
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
