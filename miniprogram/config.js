/**
 * Environment configuration.
 * Change ENV to 'prod' before submitting to WeChat review.
 */
const ENV = 'prod'; // 'dev' | 'prod'

const BASE_URLS = {
  dev: 'http://127.0.0.1:8000/api/v1',
  prod: 'https://www.tennisplaynow.site:8443/api/v1',
};

module.exports = {
  baseURL: BASE_URLS[ENV],
  env: ENV,
};
