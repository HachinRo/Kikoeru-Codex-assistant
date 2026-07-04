const _ = require('lodash'); 
const express = require('express');
const router = express.Router();
const { config, setConfig, sharedConfigHandle } = require('../config');
const { requireAdmin } = require('./utils/validate');

const filterConfig = (_config, option = 'read') => {
  const currentConfig = config;
  const configClone = _.cloneDeep(_config);
  delete configClone.md5secret;
  delete configClone.jwtsecret;
  if (option === 'write') {
    delete configClone.production;
    if (process.env.NODE_ENV === 'production' || currentConfig.production) {
      delete configClone.auth;
    }
  }
  return configClone;
}

// 修改配置文件
router.put('/admin', (req, res, next) => {
  if (!requireAdmin(req, res, '只有 admin 账号能修改配置文件.')) {
    return;
  }
  try {
    // Note: setConfig uses Object.assign to merge new configs
    setConfig(filterConfig(req.body.config, 'write'));
    res.send({ message: '保存成功.' })
  } catch(err) {
    next(err);
  }
});

// 获取配置文件
router.get('/admin', (req, res, next) => {
  if (!requireAdmin(req, res, '只有 admin 账号能读取管理配置文件.')) {
    return;
  }
  try {
    res.send({ config: filterConfig(config, 'read') });
  } catch(err) {
    next(err);
  }
});

router.get('/shared', (req, res, next) => {
  try {
    res.send({ sharedConfig: sharedConfigHandle.export() });
  } catch(err) {
    next(err);
  }
});

module.exports = router;
