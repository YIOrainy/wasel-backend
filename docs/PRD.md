# Project: Wasel – Intercity Delivery Platform

# Version: 1.

# Date: October 2025

# Prepared for: CTO & Development Team


**1. Overview**

Wasel is a mobile application connecting customers who need to send goods between cities
with drivers (captains) who are traveling and willing to deliver those goods for a fee. The
app’s mission is to provide a trusted, safe, and efficient delivery service while maintaining
user satisfaction and regulatory compliance.

**2. User Groups**
    1. Customer (Sender) – person who needs to send goods.
    2. Captain (Driver) – verified user who accepts and delivers goods.
    3. Admin (Operations) – backend system to monitor, verify, and manage disputes.
**3. Customer Workflow (End-to-End Experience)**

**3.1 Onboarding**

1. App Launch → Welcome Screen
    o Intro slides: What Wasel does.
    o CTA: Sign Up / Login.
2. Account Creation
    o Options: Phone number, Email, Apple/Google sign-in.
    o OTP verification for mobile number (SMS).
    o Profile setup: Name, ID (optional for trust), profile picture.
3. Home Screen
    o Search bar: “Where do you want to send?”
    o Quick actions: Send Package, Track Package, My Orders.

**3.2 Sending a Package**

1. New Order Creation
    o Pickup city & location (map + GPS).
    o Destination city & location (map + GPS).
    o Package details:
       ▪ Type (document, electronics, fragile, etc.)
       ▪ Dimensions & weight.
       ▪ Special notes (e.g., “Handle with care”).
2. Price Estimation & Payment Options
    o Suggested delivery fee based on distance & market rates.
    o Option for customer to propose custom fee.
    o Payment methods:
       ▪ Credit/debit card
       ▪ Mada/Apple Pay


```
▪ Cash on delivery (if allowed)
```
3. Captain Matching
    o Captains traveling to that destination get notified.
    o Customer sees list of available captains:
       ▪ Captain profile (photo, rating, verified status).
       ▪ Vehicle type, trip schedule.
       ▪ Estimated delivery time.
4. Booking Confirmation
    o Customer chooses a captain.
    o In-app chat & call option enabled.
    o Live tracking dashboard starts.

**3.3 During Delivery**

1. Pickup Phase
    o Captain arrives → package handover confirmation.
    o Option for photo proof at pickup.
2. In-Transit Tracking
    o Live GPS tracking of captain’s journey.
    o Push notifications:
       ▪ Captain started trip.
       ▪ Captain reached halfway point.
       ▪ Estimated arrival updates.
3. Delivery Phase
    o Customer notified when captain is near destination.
    o Receiver confirms delivery with OTP code OR digital signature.
    o Captain uploads photo proof of delivery.

**3.4 Post-Delivery**

1. Payment Settlement
    o If prepaid → auto deducted.
    o If COD → captain collects, reports, and settles through app.
2. Rating & Review
    o Customer rates captain (1–5 stars).
    o Option to leave written feedback.
3. History & Receipts
    o Customer can see past orders.
    o Downloadable receipts for each delivery.
**4. Captain Workflow (End-to-End Experience)**

**4.1 Onboarding & Verification**


1. Account Creation
    o Phone number + OTP.
    o Profile setup: Name, profile photo.
2. KYC Verification (Linked with Absher / Government APIs)
    o National ID verification.
    o Driving license check.
    o Vehicle registration check (Istimara, insurance, inspection).
3. Background & Safety Checks
    o Criminal record verification (via Absher or third-party API).
    o Bank account / IBAN for payouts.

**4.2 Home Screen (Captain App)**

- Tabs:
    o Available Orders
    o My Trips
    o Wallet / Earnings
    o Profile

**4.3 Accepting an Order**

1. Receive Notification when customer creates matching trip request.
2. Order Details Screen:
    o Pickup & drop-off cities.
    o Package details.
    o Delivery fee offered.
3. Decision: Accept / Decline.
4. Confirmation: If accepted → trip is added to “Active Orders.”

**4.4 Pickup & Delivery Flow**

1. Pickup Phase
    o Navigate to sender’s location using in-app maps.
    o Confirm pickup (OTP from customer).
    o Upload package photo as proof.
2. In-Transit Phase
    o Activate live tracking for customer.
    o ETA auto-updated.
3. Delivery Phase
    o Navigate to receiver.
    o Confirm delivery with OTP/digital signature.
    o Upload photo proof of delivery.


**4.5 Post-Delivery**

1. Earnings Settlement
    o Earnings summary after each completed trip.
    o Wallet auto-updated.
    o Weekly/monthly payout to bank account.
2. Ratings
    o Captain rates customer (mutual trust system).
    o Performance score impacts visibility & priority.
**5. Admin / Backend Features**
- Dashboard for monitoring orders in real-time.
- KYC approval & captain verification system.
- Dispute resolution panel (lost/damaged items).
- Earnings & commission management.
- Analytics: trip volume, revenue, user growth.
**6. Core Features (Must-Have)**
- OTP verification (customer & captain).
- GPS real-time tracking.
- In-app chat & call (masked numbers).
- Secure payment gateway.
- Rating & review system.
- Push notifications.
- Multi-language (Arabic / English).
**7. Future Enhancements (Nice-to-Have)**
- Loyalty program (points/rewards).
- AI-based route optimization.
- Package insurance options.
- Group chat for large delivery coordination.
- Dark mode UI.
**8. Compliance & Legal**
- Must comply with Saudi Transport Authority requirements.
- Integration with Absher API for KYC.
- Insurance & liability policy for captains.
- Customer data protection (GDPR-like compliance).


