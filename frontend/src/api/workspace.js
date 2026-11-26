import { request } from './client.js';

export const api = {
  signIn: data => request('/auth/login', { method: 'POST', body: data }),
  profile: () => request('/profile'),
  datasets: () => request('/datasets'),
  dataset: id => request('/datasets/' + id),
  upload: data => request('/datasets', { method: 'POST', body: data }),
  runs: () => request('/runs'),
  run: id => request('/runs/' + id),
  submit: data => request('/runs', { method: 'POST', body: data }),
  review: (id, data) => request('/runs/' + id + '/review', { method: 'POST', body: data }),
  reviews: () => request('/reviews'),
  calibrations: () => request('/calibrations'),
  calibration: id => request('/calibrations/' + id),
  createCalibration: data => request('/calibrations', { method: 'POST', body: data }),
  recheckRooms: () => request('/recheck-rooms'),
  audit: () => request('/audit'),
  download: path => request(path, { download: true }),
};
