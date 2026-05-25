/**
 * Centralised env access so tests don't sprinkle `process.env` everywhere.
 */
export const env = {
  baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
  apiURL: process.env.E2E_API_URL ?? 'http://127.0.0.1:8000',
  // If set, real (unmocked) LLM-touching tests will run. They cost OpenAI credits
  // and need Celery + Redis + a valid OPENAI_API_KEY in the backend.
  runRealLLM: process.env.E2E_RUN_REAL_LLM === '1',
  // Optional test-user credentials. If not set, tests that need a real authenticated
  // session will fall back to localStorage-injected fake JWTs (which won't pass
  // the backend but still let us test client-side route guards / UI states).
  testUser: {
    username: process.env.E2E_TEST_USERNAME,
    password: process.env.E2E_TEST_PASSWORD,
    email: process.env.E2E_TEST_EMAIL,
  },
};

export function hasRealTestUser(): boolean {
  return !!(env.testUser.username && env.testUser.password);
}
