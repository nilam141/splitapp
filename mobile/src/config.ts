// Single place for environment configuration.
// Debug builds: the Android emulator reaches the host machine at 10.0.2.2
// (cleartext is allowed only in debug builds, see android/app/build.gradle).
// Release builds: must be https; Android blocks cleartext there. Set the real
// host before shipping.
const DEV_API_BASE_URL = 'http://10.0.2.2:8000';
const RELEASE_API_BASE_URL = 'https://api.splitapp.example';

export const API_BASE_URL: string = __DEV__
  ? DEV_API_BASE_URL
  : RELEASE_API_BASE_URL;
