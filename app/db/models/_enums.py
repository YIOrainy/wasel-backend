import enum


class ShipmentStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    PICKED = "picked"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BidStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
