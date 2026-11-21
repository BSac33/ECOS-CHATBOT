# En-têtes de sécurité (inclus au niveau du serveur ET dans chaque location qui ajoute ses
# propres en-têtes : nginx n'hérite pas des add_header du niveau supérieur dans ce cas).
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), geolocation=(), payment=(), microphone=(self)" always;
# script-src blob: : module audio du mode vocal (AudioWorklet) ; style-src 'unsafe-inline' : PrimeVue
add_header Content-Security-Policy "default-src 'self'; script-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
