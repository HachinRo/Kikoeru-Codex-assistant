const { validationResult } = require('express-validator');

const isValidRequest = (req, res, sendMessage = true) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    if (sendMessage) {
      res.status(400).json({ errors: errors.array() });
    }
    return false;
  } else {
    return true;
  }
}

const isAdminRequest = (req) => {
  return Boolean(req.user && req.user.name === 'admin');
}

const requireAdmin = (req, res, message = '只有 admin 账号能执行此操作.') => {
  if (isAdminRequest(req)) {
    return true;
  }
  res.status(403).send({ error: message });
  return false;
}

module.exports = { isValidRequest, isAdminRequest, requireAdmin };
