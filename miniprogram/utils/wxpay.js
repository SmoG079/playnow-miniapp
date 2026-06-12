const app = getApp();

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

    // 2. Call wx.requestPayment
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
