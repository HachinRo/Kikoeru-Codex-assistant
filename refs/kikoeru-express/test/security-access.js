//eslint-disable-next-line node/no-unpublished-require
const chai = require('chai');
const expect = chai.expect;
const { isAdminRequest, requireAdmin } = require('../routes/utils/validate');
const { redactTranslateTask } = require('../routes/utils/translate');

describe('security access helpers', function() {
  it('denies admin-only actions when no authenticated admin is present', function() {
    const res = {
      statusCode: 200,
      body: null,
      status(code) {
        this.statusCode = code;
        return this;
      },
      send(body) {
        this.body = body;
        return this;
      },
    };

    expect(isAdminRequest({})).to.equal(false);
    expect(requireAdmin({}, res)).to.equal(false);
    expect(res.statusCode).to.equal(403);
    expect(res.body).to.have.property('error');
  });

  it('redacts private translate task fields before API responses', function() {
    const task = redactTranslateTask({
      id: 7,
      work_id: 42,
      audio_path: '/Volumes/TOSHIBA/AMSR/RJ00000001/private-track.mp3',
      status: 1,
      worker_name: 'worker-1',
      worker_status: 'transcripting 70%',
      title: 'private title',
    });

    expect(task).to.not.have.property('audio_path');
    expect(task).to.not.have.property('worker_name');
    expect(task).to.not.have.property('worker_status');
    expect(task.audio_file).to.equal('private-track.mp3');
    expect(task.worker_active).to.equal(true);
  });

  it('redacts Windows-style translate task paths on non-Windows hosts', function() {
    const task = redactTranslateTask({
      id: 8,
      audio_path: ['C:', 'AMSR', 'RJ00000002', 'private-track-2.mp3'].join('\\'),
      worker_name: '',
      worker_status: '',
    });

    expect(task.audio_file).to.equal('private-track-2.mp3');
  });
});
