from enum import StrEnum


class Role(StrEnum):
    DMD = "dmd"
    DELEGATE = "delegate"
    EMPLOYEE = "employee"


class OwnerScope(StrEnum):
    UNIT = "unit"  # the whole SBU
    DEPARTMENT = "department"
    FUNCTION = "function"
    SHARED = "shared"  # several departments / functions, see SubscriptionShare


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class VendorCategory(StrEnum):
    AI = "ai"
    DESIGN = "design"
    PRODUCTIVITY = "productivity"
    DEV = "dev"
    OTHER = "other"


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"
    USAGE = "usage"
    ONE_TIME = "one_time"


class SubscriptionType(StrEnum):
    INDIVIDUAL = "individual"
    TEAM = "team"
    API_CREDIT = "api_credit"
    ONE_TIME = "one_time"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PENDING_PAYMENT = "pending_payment"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AssignmentStatus(StrEnum):
    ACTIVE = "active"
    REVOKE_PENDING = "revoke_pending"
    REVOKED = "revoked"


class RequestType(StrEnum):
    NEW = "new"
    RENEWAL = "renewal"
    UPGRADE = "upgrade"
    CANCEL = "cancel"
    PROPOSAL = "proposal"  # new tool for a department/unit that does not have it yet


class RequestStatus(StrEnum):
    PENDING_MANAGER = "pending_manager"
    PENDING_DMD = "pending_dmd"
    ON_HOLD = "on_hold"
    INFO_NEEDED = "info_needed"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    APPROVED = "approved"
    HANDOVER_PENDING = "handover_pending"
    ACTIVE = "active"
    ENDED = "ended"
    FULFILLED = "fulfilled"  # approved proposal turned into a subscription


class ApprovalStep(StrEnum):
    MANAGER = "manager"
    DMD = "dmd"


class HandoverMethod(StrEnum):
    VAULT = "vault"
    APPOINTMENT = "appointment"
    COLLEAGUE = "colleague"


class OtpPurpose(StrEnum):
    LOGIN = "login"
    REVEAL = "reveal"
