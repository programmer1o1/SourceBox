"""SourceBox test suite."""

import tempfile

from sourcebox import install_manifest

# Bridges record what they install in a manifest that SourceBox undoes on close.
# Point it at a scratch folder so tests never touch the real one (or real games).
install_manifest.use(
    install_manifest.InstallManifest(tempfile.mkdtemp(prefix="sourcebox-test-manifest-"))
)
