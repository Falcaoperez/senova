-- Solo para el entorno local de pruebas y los nombres predeterminados del proyecto.
CREATE DATABASE IF NOT EXISTS test_senova CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON test_senova.* TO 'gesicom_app'@'%';
