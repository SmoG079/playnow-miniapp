const app = getApp();

/**
 * Initiate WeChat payment for a booking.
 * @param {number} bookingId - The booking order ID
 * @returns {Promise} Resolves when payment is done
 */
async function payBooking(bookingId) {
  try {
    // 1. Get payment params from backend
    const payParams = await app.request({
      url: `/bookings/${bookingId}/pay`,
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

module.exports = { payBooking };
