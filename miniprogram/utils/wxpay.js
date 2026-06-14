const app = getApp();

/**
 * Validate WeChat payment parameters.
 * @param {object} payParams
 * @returns {string|null} Error message if invalid, null if valid
 */
function validatePayParams(payParams) {
  const required = ['timeStamp', 'nonceStr', 'package', 'signType', 'paySign'];
  for (const key of required) {
    if (!payParams[key]) {
      return `缺少支付参数: ${key}`;
    }
  }
  return null;
}

/**
 * Initiate WeChat payment for any pending order.
 * @param {number} orderId - The booking order ID
 * @returns {Promise} Resolves when payment is done
 */
async function payOrder(orderId) {
  try {
    // 1. Get payment params from backend
    const payParams = await app.request({
      url: `/bookings/${orderId}/pay`,
      method: 'POST',
    });

    // 2. Validate params
    const validationError = validatePayParams(payParams);
    if (validationError) {
      wx.showToast({ title: validationError, icon: 'none' });
      return Promise.reject(new Error(validationError));
    }

    // 3. Call wx.requestPayment
    return new Promise((resolve, reject) => {
      wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: payParams.signType,
        paySign: payParams.paySign,
        success: () => resolve(true),
        fail: (err) => {
          if (err.errMsg.includes('cancel')) {
            reject(new Error('用户取消支付'));
          } else {
            reject(err);
          }
        },
      });
    });
  } catch (e) {
    throw e;
  }
}

/**
 * Initiate WeChat payment for a tournament registration.
 * @param {number} tournamentId - The tournament ID
 * @returns {Promise} Resolves when payment is done
 */
async function payTournament(tournamentId) {
  try {
    const payParams = await app.request({
      url: `/tournaments/${tournamentId}/pay`,
      method: 'POST',
    });

    const validationError = validatePayParams(payParams);
    if (validationError) {
      wx.showToast({ title: validationError, icon: 'none' });
      return Promise.reject(new Error(validationError));
    }

    return new Promise((resolve, reject) => {
      wx.requestPayment({
        timeStamp: payParams.timeStamp,
        nonceStr: payParams.nonceStr,
        package: payParams.package,
        signType: payParams.signType,
        paySign: payParams.paySign,
        success: () => resolve(true),
        fail: (err) => {
          if (err.errMsg.includes('cancel')) {
            reject(new Error('用户取消支付'));
          } else {
            reject(err);
          }
        },
      });
    });
  } catch (e) {
    throw e;
  }
}

/**
 * Initiate WeChat payment for a booking. (delegates to payOrder)
 * @param {number} bookingId - The booking order ID
 * @returns {Promise} Resolves when payment is done
 */
async function payBooking(bookingId) {
  return payOrder(bookingId);
}

module.exports = { payOrder, payBooking, payTournament };
