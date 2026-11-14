// Keep credentials on stdin, never in command-line arguments or console output.
const fs = require('node:fs');
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
for (const method of ['log', 'warn', 'error', 'info', 'debug']) {
    console[method] = () => {};
}
// Node 22+ exposes its own navigator; the upstream script supplies its browser stub.
delete globalThis.navigator;
const signer = require('./vendor/tripstar/xhs_xs_xsc_56.cjs');
const signature = signer.get_request_headers_params(request.path, request.payload, request.a1, 'POST');
process.stdout.write(JSON.stringify(signature));
