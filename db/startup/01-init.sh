#!/bin/bash
echo ">> rss: ensuring tablespace and user ${APP_USER} in FREEPDB1"
if ! "$ORACLE_HOME"/bin/sqlplus -s "/ as sysdba" <<EOF
WHENEVER SQLERROR EXIT FAILURE
ALTER SESSION SET CONTAINER = FREEPDB1;
CREATE TABLESPACE IF NOT EXISTS rss_data
  DATAFILE '/opt/oracle/oradata/FREE/FREEPDB1/rss_data01.dbf'
  SIZE 200M AUTOEXTEND ON NEXT 100M MAXSIZE 8G;
CREATE USER IF NOT EXISTS ${APP_USER} IDENTIFIED BY "${APP_USER_PASSWORD}"
  DEFAULT TABLESPACE rss_data QUOTA UNLIMITED ON rss_data;
GRANT DB_DEVELOPER_ROLE TO ${APP_USER};
EXIT
EOF
then
  echo ">> rss: ERROR creating tablespace/user"
  return 0
fi
echo ">> rss: init done"
