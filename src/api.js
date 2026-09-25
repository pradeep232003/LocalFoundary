const fragment = new URLSearchParams(location.hash.slice(1));
if (fragment.has('token')) {
  sessionStorage.setItem('foundry-token', fragment.get('token'));
  history.replaceState(null, '', location.pathname);
}

const authorization = () => 'Bearer ' + (sessionStorage.getItem('foundry-token') || '');

export async function request(path, body, options = {}) {
  const headers = { Authorization: authorization() };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch('/api' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Request failed (${response.status})`);
  }
  return options.blob ? response.blob() : response.json();
}

export async function download(project) {
  const blob = await request(`/projects/${project.id}/download`, undefined, { blob: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = project.name.replace(/[^a-z0-9-]/gi, '-') + '.zip';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

export async function downloadRecovery(project, item) {
  const blob = await request(`/projects/${project.id}/recovery/${item.id}`, undefined, { blob: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = item.filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

export async function downloadMobile(projectId, item) {
  const blob = await request(`/projects/${projectId}/mobile/builds/${item.id}/download`, undefined, {
    blob: true,
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = item.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

export async function downloadRelease(project) {
  const blob = await request(
    `/projects/${project.id}/release`,
    { source_digest: project.source_digest },
    { blob: true },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = project.name.replace(/[^a-z0-9-]/gi, '-') + '-release.zip';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

export async function importRecovery(file, password, name = '') {
  const response = await fetch('/api/recovery/import', {
    method: 'POST',
    headers: {
      Authorization: authorization(),
      'Content-Type': 'application/octet-stream',
      'X-Foundry-Recovery-Password': encodeURIComponent(password),
      'X-Foundry-Recovery-Name': encodeURIComponent(name),
    },
    body: file,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : `Import failed (${response.status})`);
  }
  return response.json();
}
