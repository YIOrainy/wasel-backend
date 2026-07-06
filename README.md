# wasel-backend

## Run with Docker

```bash
docker compose up --build
```

## DB Schema

```mermaid
erDiagram
    users ||--o| capitan_profiles : "has (captain)"
    users ||--o{ shipments : "sends (sender_id)"
    users |o--o{ shipments : "delivers (capitan_id)"
    users ||--o{ bids : "places (capitan_id)"
    users ||--o{ saved_locations : "saves"
    users ||--o{ devices : "registers"
    shipments ||--o{ bids : "receives"
    shipments ||--o{ ratings : "rated by (no FK yet)"

    users {
        uuid user_id PK
        string name
        string email UK
        string phone_number UK
        string avatar_url
        string role
    }

    capitan_profiles {
        uuid capitan_profile_id PK
        uuid user_id FK,UK
        float rating
        int total_trips
    }

    shipments {
        uuid shipment_id PK
        uuid sender_id FK
        uuid capitan_id FK "nullable"
        string pickup_city
        string destination_city
        float pickup_lat
        float pickup_lng
        float destination_lat
        float destination_lng
        enum status "pending|accepted|picked|out_for_delivery|delivered|expired|cancelled"
        timestamptz expires_at
        string receiver_phone_number
        timestamptz expected_pickup_time
        timestamptz expected_delivery_time
        bool pickup_asap
        string special_handling
        string photo_url
        numeric price "set on bid accept"
        string pickup_otp
        string delivery_otp
        timestamptz accepted_at
        timestamptz picked_at
        timestamptz out_for_delivery_at
        timestamptz delivered_at
    }

    bids {
        uuid bid_id PK
        uuid shipment_id FK "unique with capitan_id"
        uuid capitan_id FK
        numeric price "must be > 0"
        enum status "pending|accepted|rejected"
    }

    saved_locations {
        uuid saved_location_id PK
        uuid user_id FK "unique with lat,lng"
        string kind
        string label
        string address_line
        string city
        float lat
        float lng
        string notes
    }

    devices {
        uuid device_id PK
        uuid user_id FK
        string fcm_token UK
        string platform "ios|android"
    }

    ratings {
        uuid rating_id PK
        uuid shipment_id "no FK yet"
        uuid sender_id "no FK yet"
        uuid capitan_id "no FK yet"
        int stars
        string comment
    }
```

All tables also carry `created_at` / `updated_at` (timestamptz), omitted above for brevity. The DB additionally contains [Procrastinate](https://procrastinate.readthedocs.io/) job-queue tables (installed by migration), not shown here.
