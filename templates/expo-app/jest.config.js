/** @type {import('jest').Config} */
module.exports = {
  preset: 'jest-expo',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  collectCoverageFrom: ['src/**/*.{ts,tsx}', '!src/**/*.generated.ts'],
  testMatch: ['<rootDir>/__tests__/**/*.test.{ts,tsx}'],
};
