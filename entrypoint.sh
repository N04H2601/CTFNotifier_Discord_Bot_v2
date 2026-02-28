#!/bin/sh
 
# Get UID/GID of the mounted volume
VOLUME_UID=$(stat -c "%u" /srcp)
VOLUME_GID=$(stat -c "%g" /src)
 
# If volume is owned by a different UID/GID, adjust container user
if [ "$VOLUME_UID" -ne "$(id -u bot)" ] || [ "$VOLUME_GID" -ne "$(id -g bot)" ]; then
    echo "Adjusting bot UID/GID to match volume ($VOLUME_UID:$VOLUME_GID)"
    usermod -u $VOLUME_UID bot
    groupmod -g $VOLUME_GID botgroup
    chown -R bot:botgroup /src  # Fix permissions after UID/GID change
fi
 
# Run the original command
exec "$@"

# Source : https://linuxvox.com/blog/understanding-user-file-ownership-in-docker-how-to-avoid-changing-permissions-of-linked-volumes/#solution-2-use-named-volumes-instead-of-bind-mounts