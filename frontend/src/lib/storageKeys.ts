// localStorage keys shared by auth, basket and the signup return intent.
// Kept import-free so auth.ts can clear them without an auth → basket → api → auth cycle.
export const BASKET_KEY = 'uvarto.basket.v1';
export const RETURN_KEY = 'uvarto.return.v1';
export const PENDING_PLAN_KEY = 'uvarto.pendingPlan.v1';
