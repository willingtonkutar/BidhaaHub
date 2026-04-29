# Daraja M-Pesa Integration - Quick Start Guide

## Your Question: "Do I need an API key for the Daraja API?"

**YES** - You need several credentials from Safaricom Daraja. Here's exactly what to do:

---

## 📋 Step-by-Step Setup

### 1. Register for Daraja (5 minutes)

1. Go to: https://daraja.safaricom.co.ke
2. Click "Create Account" (if you don't have one)
   - Fill in: Email, password, business details
   - Business type: Select "Grocery Store" or "Retail"
3. Verify your email
4. Log in to the Daraja dashboard

### 2. Create an M-Pesa App

1. In Daraja dashboard, go to **"Apps"** or **"Create New App"**
2. Click **"Create a New App"** button
3. Fill in the form:
   - **App Name**: "BidhaaHub Mobile Money"
   - **App Type**: "Web" (or "Mobile Web")
   - **Description**: "Accept M-Pesa payments for e-commerce"
4. Click "Create"
5. You'll see your **Consumer Key** and **Consumer Secret** generated

### 3. Get Your Business Shortcode

1. In Daraja dashboard, look for **"Business Details"** or **"Settings"**
2. Your **Business Short Code** is usually:
   - A **Paybill Number** (if you have M-Pesa for Business)
   - Or a **Till Number** (if you have M-Pesa Merchant)
   - Example: `123456`
3. If you don't have one, apply for M-Pesa for Business through Safaricom

### 4. Get Your Passkey

1. Still in Business Details section, look for **"Passkey"** or **"M2M Passkey"**
2. This is a secret key Safaricom provides (usually 40+ characters)
3. Keep this safe! (It's like a password)

### 5. Note Down Your Credentials

You should now have 4 credentials:

```
Consumer Key:    xxxxxxxxxxxxxxxxxxxx
Consumer Secret: xxxxxxxxxxxxxxxxxxxx
Business Shortcode: 123456
Passkey:         xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 🔑 Enter Credentials in BidhaaHub

1. Open BidhaaHub as Admin: http://127.0.0.1:8000
2. Navigate to: **💳 Payments** (in sidebar)
3. Scroll down to: **🔐 Daraja M-Pesa Setup** section
4. Fill in the form:
   - Consumer Key: Paste your Consumer Key
   - Consumer Secret: Paste your Consumer Secret
   - Shortcode: Paste your Business Shortcode (e.g., 123456)
   - Passkey: Paste your Passkey
5. Click **"Save Daraja Keys"**

> ⚠️ In production, these credentials should be encrypted and stored in environment variables, never in the frontend.

---

## 🧪 Testing Daraja Integration

### Test Mode (Sandbox)
Daraja has a **Sandbox environment** for testing:
- URL: https://sandbox.safaricom.co.ke
- Use test credentials (no real money charged)
- Test with test phone numbers Safaricom provides

### Steps to Test:
1. Get sandbox credentials from Daraja dashboard
2. Enter them in BidhaaHub admin panel
3. Make a test checkout with a test phone number
4. M-Pesa prompt should appear on the phone (or simulator)
5. Confirm payment in prompt
6. Order status updates to "Paid"

---

## 💰 Real Money (Production)

Once testing passes:
1. Switch to **Production credentials** in Daraja
2. Replace sandbox Consumer Key/Secret in BidhaaHub admin
3. Customers will see real M-Pesa prompts on their phones
4. Real money will be charged to their accounts

---

## 🛠️ What Happens When Customer Checks Out

### Current (Status Quo - Doesn't Work Yet)
1. Customer fills checkout form
2. Selects "M-Pesa Daraja" as payment method
3. Clicks "Place Order"
4. Backend returns: `{ status: "pending" }` (MOCK - no real payment)

### After I Wire Real Daraja API (Next Step)
1. Customer fills checkout form
2. Selects "M-Pesa Daraja" as payment method
3. Clicks "Place Order"
4. Backend calls **Daraja STK Push API**:
   ```
   POST https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest
   {
     "BusinessShortCode": 123456,
     "Password": "base64_encoded_key",
     "Timestamp": "20260428142300",
     "TransactionType": "CustomerPayBillOnline",
     "Amount": 15000,
     "PartyA": 254720123456,  // Customer's phone
     "PartyB": 123456,         // Your shortcode
     "PhoneNumber": 254720123456,
     "CallBackURL": "https://yourapp.com/api/daraja/callback",
     "AccountReference": "ORDER#123",
     "TransactionDesc": "Payment for Order #123"
   }
   ```
5. Customer gets **M-Pesa prompt on their phone**:
   ```
   Enter your M-Pesa PIN to complete this transaction
   Amount: 150 KES
   ```
6. Customer enters PIN, payment completes
7. Safaricom sends callback to your webhook:
   ```
   POST /api/daraja/callback
   {
     "Body": {
       "stkCallback": {
         "MerchantRequestID": "...",
         "CheckoutRequestID": "...",
         "ResultCode": 0,  // 0 = success, non-zero = failed
         "CallbackMetadata": {
           "Item": [
             { "Name": "Amount", "Value": 150 },
             { "Name": "Phone", "Value": 254720123456 },
             ...
           ]
         }
       }
     }
   }
   ```
8. Backend updates order: `status = "paid"`, `payment_status = "completed"`
9. Customer sees order confirmation

---

## 🔗 API Endpoints You'll Need

### Daraja APIs
- **STK Push**: Sends payment prompt to customer phone
  - `POST https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest`
- **STK Query**: Check if payment prompt was sent
  - `POST https://api.safaricom.co.ke/mpesa/stkpushquery/v1/query`
- **Callback**: Receives payment status updates (passive - Daraja calls you)
  - Your webhook: `POST /api/daraja/callback`

### Your BidhaaHub APIs (Already Exist)
- `POST /payments/initiate` - Start payment (currently returns mock response)
- `POST /payments/callback` - (Will be created to handle Daraja callbacks)
- `GET /orders/{id}/status` - Check order status

---

## 🚨 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "Invalid Consumer Key" | Check credentials are exact (copy-paste from Daraja dashboard) |
| "Phone number invalid" | Format must be 254XXXXXXXXX (12 digits, starts with 254 for Kenya) |
| "Insufficient balance" | Use sandbox mode for testing (no real money charged) |
| "Callback not received" | Ensure your webhook URL is publicly accessible (not localhost) |
| "STK prompt doesn't appear" | Check phone number is correct and has M-Pesa enabled |

---

## 💡 Daraja Costs

- **STK Push**: ~0.50 KES per request (whether successful or not)
- **Failed transactions**: Still charged, but money returned
- **Successful transaction**: Safaricom takes 2-3% commission

Example: 10,000 KES order → Safaricom takes ~200-300 KES

---

## 📚 Daraja Documentation

Full API docs (if you need advanced features):
- https://daraja.safaricom.co.ke/docs
- Look for: "STK Push", "Callbacks", "B2B", "B2C" sections

---

## 🎯 Summary: What To Do NOW

1. ✅ Register at https://daraja.safaricom.co.ke
2. ✅ Create an M-Pesa app → Get Consumer Key & Secret
3. ✅ Get your Business Shortcode from M-Pesa for Business
4. ✅ Get your Passkey from Daraja dashboard
5. ✅ Enter all 4 credentials in BidhaaHub admin panel (💳 Payments)
6. ✅ Tell me when you have the credentials
7. ✅ I'll wire the real STK Push API to make it actually work

---

**When you're ready, give me your 4 credentials and I'll implement the real Daraja integration!**
