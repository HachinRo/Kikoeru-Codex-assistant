const path = require('path');

const redactTranslateTask = (task) => {
  const {
    audio_path,
    worker_name,
    worker_status,
    ...safeTask
  } = task;
  const normalizedAudioPath = audio_path ? audio_path.replace(/\\/g, '/') : '';

  return Object.assign(safeTask, {
    audio_file: normalizedAudioPath ? path.posix.basename(normalizedAudioPath) : '',
    worker_active: Boolean(worker_name),
  });
}

module.exports = { redactTranslateTask };
