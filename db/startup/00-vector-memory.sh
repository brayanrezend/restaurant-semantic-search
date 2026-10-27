#!/bin/bash
rss_vmem=$("$ORACLE_HOME"/bin/sqlplus -s "/ as sysdba" <<EOF
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT value FROM v\$parameter WHERE name = 'vector_memory_size';
EXIT
EOF
)
if [ "$(echo "$rss_vmem" | tr -d '[:space:]')" = "0" ]; then
  echo ">> rss: enabling vector memory (${VECTOR_MEMORY_SIZE:-256M}) and restarting the instance"
  "$ORACLE_HOME"/bin/sqlplus -s "/ as sysdba" <<EOF
ALTER SYSTEM SET vector_memory_size = ${VECTOR_MEMORY_SIZE:-256M} SCOPE=SPFILE;
SHUTDOWN IMMEDIATE;
STARTUP;
ALTER PLUGGABLE DATABASE ALL OPEN;
EXIT
EOF
fi
