#!/bin/sh
# clockdrift 安装：复制到 ~/bin 并加执行位
set -e
SRC="$(cd "$(dirname "$0")" && pwd)/clockdrift.py"
mkdir -p "$HOME/bin"
cp "$SRC" "$HOME/bin/clockdrift"
chmod +x "$HOME/bin/clockdrift"
echo "installed: $HOME/bin/clockdrift"
case ":$PATH:" in
  *":$HOME/bin:"*) ;;
  *) echo "NOTE: $HOME/bin not in PATH — add it to use 'clockdrift' directly";;
esac
"$HOME/bin/clockdrift" check --samples 1 --timeout 5 && echo "smoke test: OK"
