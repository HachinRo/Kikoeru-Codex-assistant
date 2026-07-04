const express = require('express');
const router = express.Router();
const { check, validationResult } = require('express-validator'); // 后端校验
const { md5 } = require('../auth/utils');
const db = require('../database/db');
const { isAdminRequest, requireAdmin } = require('./utils/validate');


// 创建一个新用户 (只有 admin 账号拥有权限)
router.post('/user', [
  check('name')
    .isLength({ min: 5 })
    .withMessage('用户名长度至少为 5'),
  check('password')
    .isLength({ min: 5 })
    .withMessage('密码长度至少为 5'),
  check('group')
    .custom(value => {
      if (value !== 'user' && value !== 'guest') {
        throw new Error(`用户组名称必须为 ['user', 'guest'] 的一个.`)
      }
      return true
    })
], (req, res, next) => {
  // Finds the validation errors in this request and wraps them in an object with handy functions
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(422).send({ errors: errors.array() });
  }

  const user = {
    name: req.body.name,
    password: req.body.password,
    group: req.body.group
  };

  if (!requireAdmin(req, res, '只有 admin 账号能创建新用户.')) {
    return;
  }
  db.createUser({
    name: user.name,
    password: md5(user.password),
    group: user.group
  })
    .then(() => res.send({ message: `用户 ${user.name} 创建成功.` }))
    .catch((err) => {
      if (err.message.indexOf('已存在') !== -1) {
        res.status(403).send({ error: err.message });
      } else {
        next(err);
      }
    });
});

// 更新用户密码
router.put('/user', [
  check('name')
    .isLength({ min: 5 })
    .withMessage('用户名长度至少为 5'),
  check('newPassword')
    .isLength({ min: 5 })
    .withMessage('密码长度至少为 5')
], (req, res, next) => {
  // Finds the validation errors in this request and wraps them in an object with handy functions
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(422).json({errors: errors.array()});
  }

  const user = {
    name: req.body.name
  };
  const newPassword = md5(req.body.newPassword);

  if (isAdminRequest(req) || (req.user && req.user.name === user.name)) {
    db.updateUserPassword(user, newPassword)
      .then(() => res.send({ message: '密码修改成功.' }))
      .catch((err) => {
        if (err.message.indexOf('用户名错误.') !== -1) {
          res.status(403).send({ error: '用户名错误.' });
        } else {
          next(err);
        }
      });
  } else {
    res.status(403).send({ error: '只能修改自己账号的密码.' });
  }
});

// 删除用户 (仅 admin 账号拥有权限)
router.delete('/user', (req, res, next) => {
  const users = req.body.users

  if (!requireAdmin(req, res, '只有 admin 账号能删除用户.')) {
    return;
  }
  if (!users.find(user => user.name === 'admin')) {
    db.deleteUser(users)
      .then(() => {
        res.send({ message: '删除成功.' });
      })
      .catch((err) => {
        next(err);
      });
  } else {
    res.status(403).send({ error: '不能删除内置的管理员账号.' });
  }
});

// 获取所有用户
router.get('/users', (req, res, next) => {
  if (!requireAdmin(req, res, '只有 admin 账号能浏览用户.')) {
    return;
  }
  db.knex('t_user')
  .select('name', 'group')
  .then((users) => {
    res.send({ users });
  })
  .catch((err) => {
    next(err);
  });
});

module.exports = router;
