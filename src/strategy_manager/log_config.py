"""
Flexible logging configuration supporting multiple backends.
Supports local files, ELK, Loki, and other remote systems.
"""
import os
import logging
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LogBackendFactory:
    """Factory to create appropriate log handler based on configuration."""
    
    @staticmethod
    def create_handler(config: Dict[str, Any]) -> Optional[logging.Handler]:
        """
        Create a log handler based on configuration.
        
        Args:
            config: Configuration dict with 'type' and backend-specific settings
            
        Returns:
            logging.Handler or None
        """
        backend_type = config.get('type', 'file').lower()
        
        if backend_type == 'file':
            return LogBackendFactory._create_file_handler(config)
        elif backend_type == 'elk':
            return LogBackendFactory._create_elk_handler(config)
        elif backend_type == 'loki':
            return LogBackendFactory._create_loki_handler(config)
        elif backend_type == 'graylog':
            return LogBackendFactory._create_graylog_handler(config)
        elif backend_type == 'console':
            return logging.StreamHandler()
        else:
            raise ValueError(f"Unknown log backend type: {backend_type}")
    
    @staticmethod
    def _create_file_handler(config: Dict[str, Any]) -> logging.Handler:
        """Create RotatingFileHandler for local files."""
        filepath = config.get('path')
        if not filepath:
            raise ValueError("File path required for 'file' backend")
        
        # Create directory if it doesn't exist
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        
        max_bytes = config.get('max_bytes', 10 * 1024 * 1024)  # 10MB default
        backup_count = config.get('backup_count', 5)
        encoding = config.get('encoding', 'utf-8')
        
        return RotatingFileHandler(
            filepath,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding
        )
    
    @staticmethod
    def _create_elk_handler(config: Dict[str, Any]) -> logging.Handler:
        """Create handler for Elasticsearch/ELK."""
        try:
            from elasticsearch import Elasticsearch
            from elasticsearch.helpers import BulkIndexError
        except ImportError:
            raise ImportError("elasticsearch package required for ELK backend. Install: pip install elasticsearch")
        
        host = config.get('host', 'localhost')
        port = config.get('port', 9200)
        index = config.get('index', 'logs')
        doc_type = config.get('doc_type', '_doc')
        username = config.get('username')
        password = config.get('password')
        use_ssl = config.get('use_ssl', False)
        verify_certs = config.get('verify_certs', True)
        
        print(f"🔍 [ELK DEBUG] Creating ELK handler:")
        print(f"   Host: {host}:{port}")
        print(f"   Index: {index}")
        print(f"   Username: {username if username else 'None'}")
        print(f"   SSL: {use_ssl}")
        
        # Simple Elasticsearch handler (basic implementation)
        class ElasticsearchHandler(logging.Handler):
            def __init__(self, host, port, index, doc_type, username=None, password=None, use_ssl=False, verify_certs=True):
                super().__init__()
                
                # Build Elasticsearch connection config
                es_config = {
                    'hosts': [{'host': host, 'port': port, 'scheme': 'https' if use_ssl else 'http'}],
                }
                
                # Add authentication if credentials provided
                if username and password:
                    es_config['http_auth'] = (username, password)
                
                # SSL settings
                if use_ssl:
                    es_config['use_ssl'] = True
                    es_config['verify_certs'] = verify_certs
                
                # Set compatibility mode for older Elasticsearch versions
                # This allows ES client 9.x to work with ES server 7.x/8.x
                import os
                if not os.environ.get('ELASTIC_CLIENT_APIVERSIONING'):
                    os.environ['ELASTIC_CLIENT_APIVERSIONING'] = '1'
                
                try:
                    self.es = Elasticsearch(**es_config)
                    # Test connection
                    if self.es.ping():
                        print(f"✅ [ELK DEBUG] Connected to Elasticsearch at {host}:{port}")
                        
                        # Ensure index exists (auto-create if not)
                        if not self.es.indices.exists(index=index):
                            print(f"📋 [ELK DEBUG] Creating index '{index}'...")
                            self.es.indices.create(
                                index=index,
                                body={
                                    "mappings": {
                                        "properties": {
                                            "@timestamp": {"type": "date"},
                                            "message": {"type": "text"},
                                            "level": {"type": "keyword"},
                                            "logger": {"type": "keyword"},
                                            "module": {"type": "keyword"},
                                            "function": {"type": "keyword"},
                                            "line": {"type": "integer"}
                                        }
                                    }
                                }
                            )
                            print(f"✅ [ELK DEBUG] Index '{index}' created")
                        else:
                            print(f"✅ [ELK DEBUG] Index '{index}' already exists")
                    else:
                        print(f"⚠️ [ELK DEBUG] Elasticsearch ping failed at {host}:{port}")
                except Exception as e:
                    print(f"❌ [ELK DEBUG] Failed to connect to Elasticsearch: {e}")
                    raise
                
                self.index = index
                self.doc_type = doc_type
            
            def emit(self, record):
                try:
                    doc = self.format(record)
                    
                    # Convert timestamp to ISO 8601 format (Kibana standard)
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(record.created).isoformat()
                    
                    result = self.es.index(index=self.index, body={
                        '@timestamp': timestamp,  # Standard Kibana timestamp field
                        'message': doc,
                        'level': record.levelname,
                        'logger': record.name,
                        'module': record.module,
                        'function': record.funcName,
                        'line': record.lineno,
                    })
                    print(f"📝 [ELK DEBUG] Sent log to ELK: {record.levelname} - {record.getMessage()[:50]}")
                except Exception as e:
                    print(f"❌ [ELK DEBUG] Failed to send log to ELK: {e}")
                    self.handleError(record)
        
        return ElasticsearchHandler(host, port, index, doc_type, username, password, use_ssl, verify_certs)
    
    @staticmethod
    def _create_loki_handler(config: Dict[str, Any]) -> logging.Handler:
        """Create handler for Grafana Loki."""
        try:
            from pythonjsonlogger import jsonlogger
            import logging.handlers
        except ImportError:
            raise ImportError("python-json-logger package required for Loki backend. Install: pip install python-json-logger")
        
        host = config.get('host', 'localhost')
        port = config.get('port', 3100)
        url = f"http://{host}:{port}/loki/api/v1/push"
        
        # Create HTTP handler for Loki
        handler = logging.handlers.HTTPHandler(
            f"{host}:{port}",
            '/loki/api/v1/push',
            method='POST'
        )
        
        # Use JSON formatter for Loki
        formatter = jsonlogger.JsonFormatter()
        handler.setFormatter(formatter)
        
        return handler
    
    @staticmethod
    def _create_graylog_handler(config: Dict[str, Any]) -> logging.Handler:
        """Create handler for Graylog."""
        try:
            import graypy
        except ImportError:
            raise ImportError("graypy package required for Graylog backend. Install: pip install graypy")
        
        host = config.get('host', 'localhost')
        port = config.get('port', 12201)
        
        return graypy.GELFUdpHandler(host, port)


class LogConfig:
    """Main logging configuration class with multi-backend support."""
    
    @staticmethod
    def get_config() -> Dict[str, Any]:
        """
        Get logging configuration from environment variables or defaults.
        
        Environment variables:
        - LOG_BACKENDS: Comma-separated list of backends (default: 'file')
          Examples: 'file', 'elk', 'loki', 'file,elk', 'file,loki,graylog'
        - LOG_FILE_PATH: Path for file backend
        - LOG_ELK_HOST: Elasticsearch host
        - LOG_ELK_PORT: Elasticsearch port
        - LOG_LOKI_HOST: Loki host
        - LOG_LOKI_PORT: Loki port
        - LOG_GRAYLOG_HOST: Graylog host
        - LOG_GRAYLOG_PORT: Graylog port
        - LOG_LEVEL: Logging level (default: INFO)
        """
        backends_str = os.getenv('LOG_BACKENDS', 'file').lower()
        backends = [b.strip() for b in backends_str.split(',')]
        level = os.getenv('LOG_LEVEL', 'INFO').upper()
        
        config = {
            'backends': backends,
            'level': level,
        }
        
        # File backend config
        if 'file' in backends:
            config['file'] = {
                'path': os.getenv('LOG_FILE_PATH'),
                'max_bytes': int(os.getenv('LOG_FILE_MAX_BYTES', 10 * 1024 * 1024)),
                'backup_count': int(os.getenv('LOG_FILE_BACKUP_COUNT', 5)),
            }
        
        # ELK backend config
        if 'elk' in backends:
            config['elk'] = {
                'host': os.getenv('LOG_ELK_HOST', 'localhost'),
                'port': int(os.getenv('LOG_ELK_PORT', 9200)),
                'index': os.getenv('LOG_ELK_INDEX', 'logs'),
                'username': os.getenv('LOG_ELK_USERNAME'),
                'password': os.getenv('LOG_ELK_PASSWORD'),
                'use_ssl': os.getenv('LOG_ELK_USE_SSL', 'false').lower() == 'true',
                'verify_certs': os.getenv('LOG_ELK_VERIFY_CERTS', 'true').lower() == 'true',
            }
        
        # Loki backend config
        if 'loki' in backends:
            config['loki'] = {
                'host': os.getenv('LOG_LOKI_HOST', 'localhost'),
                'port': int(os.getenv('LOG_LOKI_PORT', 3100)),
            }
        
        # Graylog backend config
        if 'graylog' in backends:
            config['graylog'] = {
                'host': os.getenv('LOG_GRAYLOG_HOST', 'localhost'),
                'port': int(os.getenv('LOG_GRAYLOG_PORT', 12201)),
            }
        
        return config
    
    @staticmethod
    def setup_logger(
        logger_name: str,
        log_file: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> logging.Logger:
        """
        Setup a logger with multiple configured backends.
        
        Args:
            logger_name: Name for the logger
            log_file: Optional file path (overrides config)
            config: Optional config dict (uses env vars if not provided)
            
        Returns:
            Configured logger instance with all backend handlers
            
        Example:
            # Write to both file and ELK
            export LOG_BACKENDS=file,elk
            export LOG_FILE_PATH=/var/log/trading.log
            export LOG_ELK_HOST=elasticsearch.example.com
            logger = LogConfig.setup_logger("worker")
        """
        logger = logging.getLogger(logger_name)
        
        # Get config from environment if not provided
        if config is None:
            config = LogConfig.get_config()
        
        print(f"🔍 [LOG CONFIG DEBUG] Setting up logger '{logger_name}'")
        print(f"   Backends: {config.get('backends', ['file'])}")
        print(f"   Level: {config.get('level', 'INFO')}")
        
        # Set logging level
        level = getattr(logging, config.get('level', 'INFO'))
        logger.setLevel(level)
        
        # Avoid duplicate handlers
        if logger.handlers:
            print(f"⚠️ [LOG CONFIG DEBUG] Logger already has {len(logger.handlers)} handlers, skipping")
            return logger
        
        # Standard formatter
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        
        # Create handler for each backend
        backends = config.get('backends', ['file'])
        handler_count = 0
        errors = []
        
        print(f"🔧 [LOG CONFIG DEBUG] Creating handlers for backends: {backends}")
        
        for backend in backends:
            try:
                if backend == 'file':
                    file_config = config.get('file', {})
                    file_path = log_file or file_config.get('path')
                    if not file_path:
                        raise ValueError("File path required for 'file' backend")
                    
                    print(f"   📁 Creating file handler: {file_path}")
                    handler = LogBackendFactory.create_handler({
                        'type': 'file',
                        'path': file_path,
                        'max_bytes': file_config.get('max_bytes', 10 * 1024 * 1024),
                        'backup_count': file_config.get('backup_count', 5),
                    })
                    handler.setFormatter(formatter)
                    logger.addHandler(handler)
                    handler_count += 1
                    print(f"   ✅ File handler added")
                    
                elif backend == 'elk':
                    print(f"   🔍 Creating ELK handler...")
                    elk_config = config.get('elk', {})
                    handler = LogBackendFactory.create_handler({
                        'type': 'elk',
                        'host': elk_config.get('host'),
                        'port': elk_config.get('port'),
                        'index': elk_config.get('index'),
                        'username': elk_config.get('username'),
                        'password': elk_config.get('password'),
                        'use_ssl': elk_config.get('use_ssl'),
                        'verify_certs': elk_config.get('verify_certs'),
                    })
                    handler.setFormatter(formatter)
                    logger.addHandler(handler)
                    handler_count += 1
                    print(f"   ✅ ELK handler added")
                    
                elif backend == 'loki':
                    loki_config = config.get('loki', {})
                    handler = LogBackendFactory.create_handler({
                        'type': 'loki',
                        'host': loki_config.get('host'),
                        'port': loki_config.get('port'),
                    })
                    # Loki uses JSON formatter, don't override
                    logger.addHandler(handler)
                    handler_count += 1
                    
                elif backend == 'graylog':
                    graylog_config = config.get('graylog', {})
                    handler = LogBackendFactory.create_handler({
                        'type': 'graylog',
                        'host': graylog_config.get('host'),
                        'port': graylog_config.get('port'),
                    })
                    handler.setFormatter(formatter)
                    logger.addHandler(handler)
                    handler_count += 1
                    
            except Exception as e:
                errors.append(f"{backend}: {str(e)}")
        
        # Fallback to console if no handlers succeeded
        if handler_count == 0:
            print(f"Warning: Failed to setup all log backends: {'; '.join(errors)}")
            print(f"Falling back to console logging")
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        elif errors:
            # Log warnings for partial failures
            print(f"Warning: Some log backends failed to initialize: {'; '.join(errors)}")
        
        return logger


# Example usage
if __name__ == "__main__":
    # Local file (default)
    logger = LogConfig.setup_logger(
        "test",
        log_file="/tmp/test.log"
    )
    logger.info("Test message to file")
    
    # Or with ELK (set env var):
    # export LOG_BACKEND=elk
    # export LOG_ELK_HOST=elasticsearch.example.com
    # logger = LogConfig.setup_logger("test")
    # logger.info("Test message to ELK")
