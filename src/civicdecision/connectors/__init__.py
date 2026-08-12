"""Versioned public-data connectors."""

from civicdecision.connectors.cdc_places import CDCPlacesConnector
from civicdecision.connectors.eurostat import EurostatStatisticsConnector
from civicdecision.connectors.nasa_power import NASAPowerDailyConnector
from civicdecision.connectors.nyc_311 import NYC311Connector
from civicdecision.connectors.open_fema import OpenFEMADisasterConnector
from civicdecision.connectors.usgs_earthquakes import USGSEarthquakeConnector
from civicdecision.connectors.world_bank import WorldBankIndicatorConnector

__all__ = [
    "CDCPlacesConnector",
    "EurostatStatisticsConnector",
    "NASAPowerDailyConnector",
    "NYC311Connector",
    "OpenFEMADisasterConnector",
    "USGSEarthquakeConnector",
    "WorldBankIndicatorConnector",
]
