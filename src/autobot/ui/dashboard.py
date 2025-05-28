"""
Dashboard UI Module for AUTOBOT

This module provides the dashboard UI components for the AUTOBOT system,
following the specified design style (black background with neon green elements).
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class DashboardConfig:
    """Configuration for the dashboard UI"""
    
    def __init__(
        self,
        theme: str = "dark",
        accent_color: str = "#00FF41",  # Neon green
        background_color: str = "#000000",  # Black
        font_family: str = "Roboto Mono, monospace",
        show_sidebar: bool = True,
        sidebar_width: int = 250,
        show_header: bool = True,
        header_height: int = 60,
        show_footer: bool = True,
        footer_height: int = 40,
        layout: str = "grid",
        grid_columns: int = 12,
        grid_rows: int = 12,
        widgets: List[Dict[str, Any]] = None
    ):
        """
        Initialize dashboard configuration.
        
        Args:
            theme: UI theme ('dark' or 'light')
            accent_color: Accent color (hex)
            background_color: Background color (hex)
            font_family: Font family
            show_sidebar: Whether to show sidebar
            sidebar_width: Sidebar width in pixels
            show_header: Whether to show header
            header_height: Header height in pixels
            show_footer: Whether to show footer
            footer_height: Footer height in pixels
            layout: Layout type ('grid' or 'free')
            grid_columns: Number of grid columns
            grid_rows: Number of grid rows
            widgets: List of widget configurations
        """
        self.theme = theme
        self.accent_color = accent_color
        self.background_color = background_color
        self.font_family = font_family
        self.show_sidebar = show_sidebar
        self.sidebar_width = sidebar_width
        self.show_header = show_header
        self.header_height = header_height
        self.show_footer = show_footer
        self.footer_height = footer_height
        self.layout = layout
        self.grid_columns = grid_columns
        self.grid_rows = grid_rows
        self.widgets = widgets or []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "theme": self.theme,
            "accent_color": self.accent_color,
            "background_color": self.background_color,
            "font_family": self.font_family,
            "show_sidebar": self.show_sidebar,
            "sidebar_width": self.sidebar_width,
            "show_header": self.show_header,
            "header_height": self.header_height,
            "show_footer": self.show_footer,
            "footer_height": self.footer_height,
            "layout": self.layout,
            "grid_columns": self.grid_columns,
            "grid_rows": self.grid_rows,
            "widgets": self.widgets
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DashboardConfig':
        """Create configuration from dictionary"""
        return cls(
            theme=data.get("theme", "dark"),
            accent_color=data.get("accent_color", "#00FF41"),
            background_color=data.get("background_color", "#000000"),
            font_family=data.get("font_family", "Roboto Mono, monospace"),
            show_sidebar=data.get("show_sidebar", True),
            sidebar_width=data.get("sidebar_width", 250),
            show_header=data.get("show_header", True),
            header_height=data.get("header_height", 60),
            show_footer=data.get("show_footer", True),
            footer_height=data.get("footer_height", 40),
            layout=data.get("layout", "grid"),
            grid_columns=data.get("grid_columns", 12),
            grid_rows=data.get("grid_rows", 12),
            widgets=data.get("widgets", [])
        )

class Widget:
    """Base widget class for dashboard UI"""
    
    def __init__(
        self,
        widget_id: str,
        widget_type: str,
        title: str,
        x: int,
        y: int,
        width: int,
        height: int,
        config: Dict[str, Any] = None
    ):
        """
        Initialize widget.
        
        Args:
            widget_id: Unique widget ID
            widget_type: Widget type
            title: Widget title
            x: X position
            y: Y position
            width: Widget width
            height: Widget height
            config: Widget configuration
        """
        self.widget_id = widget_id
        self.widget_type = widget_type
        self.title = title
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.config = config or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert widget to dictionary"""
        return {
            "widget_id": self.widget_id,
            "widget_type": self.widget_type,
            "title": self.title,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "config": self.config
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Widget':
        """Create widget from dictionary"""
        return cls(
            widget_id=data["widget_id"],
            widget_type=data["widget_type"],
            title=data["title"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            config=data.get("config", {})
        )

class ChartWidget(Widget):
    """Chart widget for dashboard UI"""
    
    def __init__(
        self,
        widget_id: str,
        title: str,
        x: int,
        y: int,
        width: int,
        height: int,
        chart_type: str = "line",
        data_source: str = "",
        refresh_interval: int = 60,
        config: Dict[str, Any] = None
    ):
        """
        Initialize chart widget.
        
        Args:
            widget_id: Unique widget ID
            title: Widget title
            x: X position
            y: Y position
            width: Widget width
            height: Widget height
            chart_type: Chart type ('line', 'bar', 'candlestick', etc.)
            data_source: Data source for chart
            refresh_interval: Refresh interval in seconds
            config: Widget configuration
        """
        super().__init__(
            widget_id=widget_id,
            widget_type="chart",
            title=title,
            x=x,
            y=y,
            width=width,
            height=height,
            config=config or {}
        )
        
        self.chart_type = chart_type
        self.data_source = data_source
        self.refresh_interval = refresh_interval
        
        self.config.update({
            "chart_type": chart_type,
            "data_source": data_source,
            "refresh_interval": refresh_interval
        })
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChartWidget':
        """Create chart widget from dictionary"""
        config = data.get("config", {})
        
        return cls(
            widget_id=data["widget_id"],
            title=data["title"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            chart_type=config.get("chart_type", "line"),
            data_source=config.get("data_source", ""),
            refresh_interval=config.get("refresh_interval", 60),
            config=config
        )

class TableWidget(Widget):
    """Table widget for dashboard UI"""
    
    def __init__(
        self,
        widget_id: str,
        title: str,
        x: int,
        y: int,
        width: int,
        height: int,
        data_source: str = "",
        columns: List[Dict[str, Any]] = None,
        page_size: int = 10,
        refresh_interval: int = 60,
        config: Dict[str, Any] = None
    ):
        """
        Initialize table widget.
        
        Args:
            widget_id: Unique widget ID
            title: Widget title
            x: X position
            y: Y position
            width: Widget width
            height: Widget height
            data_source: Data source for table
            columns: Table columns
            page_size: Number of rows per page
            refresh_interval: Refresh interval in seconds
            config: Widget configuration
        """
        super().__init__(
            widget_id=widget_id,
            widget_type="table",
            title=title,
            x=x,
            y=y,
            width=width,
            height=height,
            config=config or {}
        )
        
        self.data_source = data_source
        self.columns = columns or []
        self.page_size = page_size
        self.refresh_interval = refresh_interval
        
        self.config.update({
            "data_source": data_source,
            "columns": columns or [],
            "page_size": page_size,
            "refresh_interval": refresh_interval
        })
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TableWidget':
        """Create table widget from dictionary"""
        config = data.get("config", {})
        
        return cls(
            widget_id=data["widget_id"],
            title=data["title"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            data_source=config.get("data_source", ""),
            columns=config.get("columns", []),
            page_size=config.get("page_size", 10),
            refresh_interval=config.get("refresh_interval", 60),
            config=config
        )

class MetricWidget(Widget):
    """Metric widget for dashboard UI"""
    
    def __init__(
        self,
        widget_id: str,
        title: str,
        x: int,
        y: int,
        width: int,
        height: int,
        metric_type: str = "number",
        data_source: str = "",
        prefix: str = "",
        suffix: str = "",
        format: str = "",
        refresh_interval: int = 60,
        config: Dict[str, Any] = None
    ):
        """
        Initialize metric widget.
        
        Args:
            widget_id: Unique widget ID
            title: Widget title
            x: X position
            y: Y position
            width: Widget width
            height: Widget height
            metric_type: Metric type ('number', 'percentage', 'currency', etc.)
            data_source: Data source for metric
            prefix: Prefix for metric value
            suffix: Suffix for metric value
            format: Format string for metric value
            refresh_interval: Refresh interval in seconds
            config: Widget configuration
        """
        super().__init__(
            widget_id=widget_id,
            widget_type="metric",
            title=title,
            x=x,
            y=y,
            width=width,
            height=height,
            config=config or {}
        )
        
        self.metric_type = metric_type
        self.data_source = data_source
        self.prefix = prefix
        self.suffix = suffix
        self.format = format
        self.refresh_interval = refresh_interval
        
        self.config.update({
            "metric_type": metric_type,
            "data_source": data_source,
            "prefix": prefix,
            "suffix": suffix,
            "format": format,
            "refresh_interval": refresh_interval
        })
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MetricWidget':
        """Create metric widget from dictionary"""
        config = data.get("config", {})
        
        return cls(
            widget_id=data["widget_id"],
            title=data["title"],
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            metric_type=config.get("metric_type", "number"),
            data_source=config.get("data_source", ""),
            prefix=config.get("prefix", ""),
            suffix=config.get("suffix", ""),
            format=config.get("format", ""),
            refresh_interval=config.get("refresh_interval", 60),
            config=config
        )

class Dashboard:
    """Dashboard for AUTOBOT UI"""
    
    def __init__(
        self,
        dashboard_id: str,
        name: str,
        description: str = "",
        config: Optional[DashboardConfig] = None,
        widgets: List[Widget] = None
    ):
        """
        Initialize dashboard.
        
        Args:
            dashboard_id: Unique dashboard ID
            name: Dashboard name
            description: Dashboard description
            config: Dashboard configuration
            widgets: List of widgets
        """
        self.dashboard_id = dashboard_id
        self.name = name
        self.description = description
        self.config = config or DashboardConfig()
        self.widgets = widgets or []
        self.created_at = int(datetime.now().timestamp())
        self.updated_at = self.created_at
    
    def add_widget(self, widget: Widget) -> bool:
        """
        Add a widget to the dashboard.
        
        Args:
            widget: Widget to add
            
        Returns:
            bool: True if widget was added successfully
        """
        for existing_widget in self.widgets:
            if existing_widget.widget_id == widget.widget_id:
                return False
        
        self.widgets.append(widget)
        self.updated_at = int(datetime.now().timestamp())
        return True
    
    def remove_widget(self, widget_id: str) -> bool:
        """
        Remove a widget from the dashboard.
        
        Args:
            widget_id: ID of widget to remove
            
        Returns:
            bool: True if widget was removed successfully
        """
        for i, widget in enumerate(self.widgets):
            if widget.widget_id == widget_id:
                self.widgets.pop(i)
                self.updated_at = int(datetime.now().timestamp())
                return True
        
        return False
    
    def get_widget(self, widget_id: str) -> Optional[Widget]:
        """
        Get a widget by ID.
        
        Args:
            widget_id: Widget ID
            
        Returns:
            Widget: Widget with the specified ID, or None if not found
        """
        for widget in self.widgets:
            if widget.widget_id == widget_id:
                return widget
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert dashboard to dictionary"""
        return {
            "dashboard_id": self.dashboard_id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "widgets": [widget.to_dict() for widget in self.widgets],
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Dashboard':
        """Create dashboard from dictionary"""
        config = DashboardConfig.from_dict(data.get("config", {}))
        
        widgets = []
        for widget_data in data.get("widgets", []):
            widget_type = widget_data.get("widget_type", "")
            
            if widget_type == "chart":
                widget = ChartWidget.from_dict(widget_data)
            elif widget_type == "table":
                widget = TableWidget.from_dict(widget_data)
            elif widget_type == "metric":
                widget = MetricWidget.from_dict(widget_data)
            else:
                widget = Widget.from_dict(widget_data)
            
            widgets.append(widget)
        
        dashboard = cls(
            dashboard_id=data["dashboard_id"],
            name=data["name"],
            description=data.get("description", ""),
            config=config,
            widgets=widgets
        )
        
        if "created_at" in data:
            dashboard.created_at = data["created_at"]
        
        if "updated_at" in data:
            dashboard.updated_at = data["updated_at"]
        
        return dashboard

class DashboardManager:
    """Manager for AUTOBOT dashboards"""
    
    def __init__(self, data_dir: str = "data/dashboards"):
        """
        Initialize dashboard manager.
        
        Args:
            data_dir: Directory for storing dashboard data
        """
        self.data_dir = data_dir
        self.dashboards: Dict[str, Dashboard] = {}
        
        os.makedirs(data_dir, exist_ok=True)
        
        self._load_dashboards()
        
        logger.info(f"Dashboard Manager initialized with {len(self.dashboards)} dashboards")
    
    def _load_dashboards(self):
        """Load dashboards from files"""
        if not os.path.exists(self.data_dir):
            return
        
        for filename in os.listdir(self.data_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(self.data_dir, filename)
                
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    
                    dashboard = Dashboard.from_dict(data)
                    self.dashboards[dashboard.dashboard_id] = dashboard
                    
                    logger.debug(f"Loaded dashboard {dashboard.name} ({dashboard.dashboard_id})")
                except Exception as e:
                    logger.error(f"Error loading dashboard from {file_path}: {str(e)}")
    
    def _save_dashboard(self, dashboard: Dashboard):
        """
        Save a dashboard to file.
        
        Args:
            dashboard: Dashboard to save
        """
        file_path = os.path.join(self.data_dir, f"{dashboard.dashboard_id}.json")
        
        try:
            with open(file_path, 'w') as f:
                json.dump(dashboard.to_dict(), f, indent=2)
            
            logger.debug(f"Saved dashboard {dashboard.name} ({dashboard.dashboard_id})")
        except Exception as e:
            logger.error(f"Error saving dashboard to {file_path}: {str(e)}")
    
    def create_dashboard(
        self,
        name: str,
        description: str = "",
        config: Optional[DashboardConfig] = None
    ) -> Dashboard:
        """
        Create a new dashboard.
        
        Args:
            name: Dashboard name
            description: Dashboard description
            config: Dashboard configuration
            
        Returns:
            Dashboard: Created dashboard
        """
        dashboard_id = f"dashboard_{int(datetime.now().timestamp())}"
        dashboard = Dashboard(
            dashboard_id=dashboard_id,
            name=name,
            description=description,
            config=config
        )
        
        self.dashboards[dashboard_id] = dashboard
        self._save_dashboard(dashboard)
        
        logger.info(f"Created dashboard {name} ({dashboard_id})")
        return dashboard
    
    def get_dashboard(self, dashboard_id: str) -> Optional[Dashboard]:
        """
        Get a dashboard by ID.
        
        Args:
            dashboard_id: Dashboard ID
            
        Returns:
            Dashboard: Dashboard with the specified ID, or None if not found
        """
        return self.dashboards.get(dashboard_id)
    
    def update_dashboard(self, dashboard: Dashboard) -> bool:
        """
        Update a dashboard.
        
        Args:
            dashboard: Dashboard to update
            
        Returns:
            bool: True if update was successful
        """
        if dashboard.dashboard_id not in self.dashboards:
            return False
        
        dashboard.updated_at = int(datetime.now().timestamp())
        self.dashboards[dashboard.dashboard_id] = dashboard
        self._save_dashboard(dashboard)
        
        logger.info(f"Updated dashboard {dashboard.name} ({dashboard.dashboard_id})")
        return True
    
    def delete_dashboard(self, dashboard_id: str) -> bool:
        """
        Delete a dashboard.
        
        Args:
            dashboard_id: ID of dashboard to delete
            
        Returns:
            bool: True if deletion was successful
        """
        if dashboard_id not in self.dashboards:
            return False
        
        file_path = os.path.join(self.data_dir, f"{dashboard_id}.json")
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            
            del self.dashboards[dashboard_id]
            
            logger.info(f"Deleted dashboard {dashboard_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting dashboard {dashboard_id}: {str(e)}")
            return False
    
    def list_dashboards(self) -> List[Dict[str, Any]]:
        """
        List all dashboards.
        
        Returns:
            List: List of dashboard summaries
        """
        return [
            {
                "dashboard_id": dashboard.dashboard_id,
                "name": dashboard.name,
                "description": dashboard.description,
                "widget_count": len(dashboard.widgets),
                "created_at": dashboard.created_at,
                "updated_at": dashboard.updated_at
            }
            for dashboard in self.dashboards.values()
        ]

def create_default_trading_dashboard() -> Dashboard:
    """
    Create a default trading dashboard.
    
    Returns:
        Dashboard: Default trading dashboard
    """
    dashboard = Dashboard(
        dashboard_id="trading_dashboard",
        name="Trading Dashboard",
        description="Default trading dashboard for AUTOBOT",
        config=DashboardConfig(
            theme="dark",
            accent_color="#00FF41",  # Neon green
            background_color="#000000",  # Black
            font_family="Roboto Mono, monospace",
            show_sidebar=True,
            sidebar_width=250,
            show_header=True,
            header_height=60,
            show_footer=True,
            footer_height=40,
            layout="grid",
            grid_columns=12,
            grid_rows=12
        )
    )
    
    price_chart = ChartWidget(
        widget_id="price_chart",
        title="Price Chart",
        x=0,
        y=0,
        width=8,
        height=6,
        chart_type="candlestick",
        data_source="trading/price_data",
        refresh_interval=30
    )
    dashboard.add_widget(price_chart)
    
    order_book = TableWidget(
        widget_id="order_book",
        title="Order Book",
        x=8,
        y=0,
        width=4,
        height=6,
        data_source="trading/order_book",
        columns=[
            {"field": "price", "headerName": "Price", "type": "number", "width": 100},
            {"field": "amount", "headerName": "Amount", "type": "number", "width": 100},
            {"field": "total", "headerName": "Total", "type": "number", "width": 100}
        ],
        refresh_interval=5
    )
    dashboard.add_widget(order_book)
    
    portfolio_value = MetricWidget(
        widget_id="portfolio_value",
        title="Portfolio Value",
        x=0,
        y=6,
        width=4,
        height=2,
        metric_type="currency",
        data_source="trading/portfolio_value",
        prefix="$",
        format=",.2f",
        refresh_interval=60
    )
    dashboard.add_widget(portfolio_value)
    
    profit_loss = MetricWidget(
        widget_id="profit_loss",
        title="Profit/Loss",
        x=4,
        y=6,
        width=4,
        height=2,
        metric_type="currency",
        data_source="trading/profit_loss",
        prefix="$",
        format="+,.2f",
        refresh_interval=60
    )
    dashboard.add_widget(profit_loss)
    
    win_rate = MetricWidget(
        widget_id="win_rate",
        title="Win Rate",
        x=8,
        y=6,
        width=4,
        height=2,
        metric_type="percentage",
        data_source="trading/win_rate",
        suffix="%",
        format=".1f",
        refresh_interval=60
    )
    dashboard.add_widget(win_rate)
    
    open_positions = TableWidget(
        widget_id="open_positions",
        title="Open Positions",
        x=0,
        y=8,
        width=12,
        height=4,
        data_source="trading/open_positions",
        columns=[
            {"field": "symbol", "headerName": "Symbol", "type": "string", "width": 100},
            {"field": "side", "headerName": "Side", "type": "string", "width": 80},
            {"field": "entry_price", "headerName": "Entry Price", "type": "number", "width": 120},
            {"field": "current_price", "headerName": "Current Price", "type": "number", "width": 120},
            {"field": "quantity", "headerName": "Quantity", "type": "number", "width": 100},
            {"field": "pnl", "headerName": "P&L", "type": "number", "width": 100},
            {"field": "pnl_percent", "headerName": "P&L %", "type": "number", "width": 100}
        ],
        refresh_interval=30
    )
    dashboard.add_widget(open_positions)
    
    return dashboard

def create_dashboard_manager(data_dir: str = "data/dashboards") -> DashboardManager:
    """
    Create a new dashboard manager.
    
    Args:
        data_dir: Directory for storing dashboard data
        
    Returns:
        DashboardManager: New dashboard manager instance
    """
    return DashboardManager(data_dir)
