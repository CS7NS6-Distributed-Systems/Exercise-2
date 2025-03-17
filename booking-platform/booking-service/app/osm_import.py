import os
import json
import logging
import requests
import psycopg2
import osmium
import shapely.wkb as wkblib
from shapely.geometry import mapping, LineString, Point, MultiLineString
from shapely.ops import linemerge  # Added for merging line segments
from pathlib import Path
import xml.etree.ElementTree as ET  # Add XML parser for fallback
from collections import defaultdict
import io

# Configure logging - set to debug level to see more information
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up a debug flag to use during development
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'False').lower() == 'true'

from app.db import cockroach_conn

# WKB helper with more permissive settings
wkb_factory = osmium.geom.WKBFactory()

class RoadHandler(osmium.SimpleHandler):
    def __init__(self, db_connection, filter_road_type=None):
        super(RoadHandler, self).__init__()
        self.conn = db_connection
        self.cursor = self.conn.cursor()
        self.road_count = 0
        self.batch = []
        self.batch_size = 1000
        self.total_ways = 0
        self.skipped_ways = 0
        self.highways_found = 0
        self.node_count = 0
        self.node_cache = {}  # Cache to store node coordinates
        self.filter_road_type = filter_road_type  # Optional road type filter

        # Dictionary to hold roads grouped by name
        self.road_groups = defaultdict(list)

    # Add a node method to collect node coordinates
    def node(self, n):
        self.node_count += 1
        # Store node coordinates in cache
        self.node_cache[n.id] = (n.location.lon, n.location.lat)
        if self.node_count % 100000 == 0:
            logger.info(f"Processed {self.node_count} nodes")

    def way(self, w):
        self.total_ways += 1

        # Check if it's a road/highway
        if 'highway' not in w.tags:
            if self.total_ways % 1000 == 0:
                logger.debug(f"Processed {self.total_ways} ways, {self.highways_found} highways found, {self.skipped_ways} skipped")
            return

        # Apply road type filter if specified
        road_type = w.tags.get('highway')
        if self.filter_road_type and road_type != self.filter_road_type:
            return

        self.highways_found += 1

        # Basic check for minimum nodes
        if len(w.nodes) < 2:
            logger.debug(f"Skipping way {w.id}: too few nodes ({len(w.nodes)})")
            self.skipped_ways += 1
            return

        try:
            # Extract tags we want to store
            tags = {}
            name = None
            road_type = w.tags.get('highway')
            country = None
            region = None

            for tag in w.tags:
                tags[tag.k] = tag.v
                if tag.k == 'name':
                    name = tag.v
                elif tag.k == 'addr:country':
                    country = tag.v
                elif tag.k == 'addr:region' or tag.k == 'addr:state':
                    region = tag.v

            # Try different geometry creation approaches
            try:
                # First approach: Standard OSM linestring creation
                wkb = None
                try:
                    # Check if nodes have valid locations
                    has_valid_locations = False
                    for node in w.nodes:
                        if node.location.valid():
                            has_valid_locations = True
                            break

                    if has_valid_locations:
                        wkb = wkb_factory.create_linestring(w)
                    else:
                        logger.debug(f"Way {w.id} has no nodes with valid locations, trying manual linestring creation")
                except Exception as e:
                    logger.debug(f"Standard linestring creation failed for way {w.id}: {e}")

                # Second approach: Build linestring from node cache if standard approach fails
                if wkb is None:
                    try:
                        coords = []
                        for node in w.nodes:
                            if node.ref in self.node_cache:
                                coords.append(self.node_cache[node.ref])

                        if len(coords) >= 2:
                            from shapely.geometry import LineString
                            line = LineString(coords)
                            geojson = json.dumps(mapping(line))
                            logger.debug(f"Created manual linestring for way {w.id} with {len(coords)} points")
                        else:
                            logger.debug(f"Not enough cached coordinates for way {w.id}: {len(coords)} points")
                            self.skipped_ways += 1
                            return
                    except Exception as e:
                        logger.debug(f"Manual linestring creation failed for way {w.id}: {e}")
                        self.skipped_ways += 1
                        return
                else:
                    # Process WKB from standard approach
                    try:
                        line = wkblib.loads(wkb, hex=True)
                        if not line.is_empty:
                            geojson = json.dumps(mapping(line))
                            logger.debug(f"Created standard linestring for way {w.id}")
                        else:
                            logger.debug(f"Empty linestring for way {w.id}")
                            self.skipped_ways += 1
                            return
                    except Exception as e:
                        logger.debug(f"Error processing WKB for way {w.id}: {e}")
                        self.skipped_ways += 1
                        return

            except Exception as e:
                logger.error(f"All geometry creation methods failed for way {w.id}: {e}")
                self.skipped_ways += 1
                return

            # Store road data grouped by name for later merging
            road_data = {
                'id': w.id,
                'name': name if name else f"unnamed_road_{w.id}",  # Use ID for unnamed roads
                'road_type': road_type,
                'country': country,
                'region': region,
                'geometry': json.loads(geojson),  # Store as parsed JSON
                'tags': tags
            }

            group_key = name if name else f"unnamed_road_{w.id}"
            self.road_groups[group_key].append(road_data)

            self.road_count += 1
            if self.road_count % 100 == 0:
                logger.info(f"Processed {self.road_count} roads")

        except Exception as e:
            logger.error(f"Error processing way {w.id}: {e}")
            self.skipped_ways += 1

    def _insert_batch(self):
        if not self.batch:
            return

        try:
            args = []
            for road in self.batch:
                args.append((
                    road['id'],
                    road['name'],
                    road['road_type'],
                    road['country'],
                    road['region'],
                    road['geometry'],
                    road['tags']
                ))

            self.cursor.executemany(
                """
                INSERT INTO osm_roads
                (id, name, road_type, country, region, geometry, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                road_type = EXCLUDED.road_type,
                country = EXCLUDED.country,
                region = EXCLUDED.region,
                geometry = EXCLUDED.geometry,
                tags = EXCLUDED.tags
                """,
                args
            )
            self.conn.commit()
            self.batch = []
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error inserting batch: {e}")

    def finalize(self):
        # Process and merge roads with the same name
        logger.info(f"Merging {len(self.road_groups)} named road groups...")
        merged_count = 0

        for name, roads in self.road_groups.items():
            try:
                if len(roads) == 1:
                    # No need to merge if only one segment
                    road = roads[0]
                    self.batch.append({
                        'id': road['id'],
                        'name': road['name'],
                        'road_type': road['road_type'],
                        'country': road['country'],
                        'region': road['region'],
                        'geometry': json.dumps(road['geometry']),
                        'tags': json.dumps(road['tags'])
                    })
                else:
                    # Need to merge multiple segments
                    # Use the first road's metadata as base
                    base_road = roads[0]

                    # Create list of linestrings to merge
                    lines = []
                    for road in roads:
                        # Convert GeoJSON geometry to LineString object
                        coords = road['geometry']['coordinates']
                        if coords:
                            line = LineString(coords)
                            if not line.is_empty:
                                lines.append(line)

                    if lines:
                        # Try to merge lines into a single linestring
                        try:
                            # First attempt: linemerge for connected lines
                            merged_line = linemerge(lines)

                            # If result is still a MultiLineString, keep it as such
                            if isinstance(merged_line, MultiLineString):
                                logger.debug(f"Created MultiLineString for {name} with {len(merged_line.geoms)} parts")
                            else:
                                logger.debug(f"Successfully merged {len(lines)} segments into single line for {name}")

                            merged_geojson = json.dumps(mapping(merged_line))

                            # Add merged road to batch
                            self.batch.append({
                                'id': base_road['id'],  # Use the first road's ID
                                'name': name,
                                'road_type': base_road['road_type'],
                                'country': base_road['country'],
                                'region': base_road['region'],
                                'geometry': merged_geojson,
                                'tags': json.dumps(base_road['tags'])
                            })

                            merged_count += 1
                        except Exception as e:
                            logger.error(f"Error merging lines for {name}: {e}")
                            # Fallback: add roads individually
                            for road in roads:
                                self.batch.append({
                                    'id': road['id'],
                                    'name': road['name'],
                                    'road_type': road['road_type'],
                                    'country': road['country'],
                                    'region': road['region'],
                                    'geometry': json.dumps(road['geometry']),
                                    'tags': json.dumps(road['tags'])
                                })

                # Insert batch if reached batch size
                if len(self.batch) >= self.batch_size:
                    self._insert_batch()

            except Exception as e:
                logger.error(f"Error processing road group {name}: {e}")

        # Insert any remaining roads
        self._insert_batch()

        logger.info(f"Total ways examined: {self.total_ways}")
        logger.info(f"Total highways found: {self.highways_found}")
        logger.info(f"Total roads skipped: {self.skipped_ways}")
        logger.info(f"Total roads processed: {self.road_count}")
        logger.info(f"Total road groups merged: {merged_count}")

def fetch_roads_overpass(region="ireland", road_type=None):
    """
    Fetches road data from Overpass API for a region, optionally filtered by road type.

    Args:
        region: A string representing the region ("ireland" by default)
        road_type: Optional filter for highway type (e.g., "motorway")

    Returns:
        Path: Path to the downloaded OSM file, or None on failure.
    """
    # Try alternative Overpass endpoints if the main one fails
    overpass_endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]

    output_dir = Path("./osm_data")
    os.makedirs(output_dir, exist_ok=True)

    # Build the appropriate query based on parameters
    if region.lower() == "ireland":
        # For Ireland, use a more direct name-based approach with wide area
        if road_type:
            # Query filtered by road type (e.g., motorways only)
            # This uses a bounding box that covers all of Ireland
            overpass_query = f'''
            [out:xml][timeout:600];
            // Ireland bounding box
            way["highway"="{road_type}"](51.3,-11.0,55.5,-5.0);
            (._;>;);
            out body;
            '''
        else:
            # Query for all highways
            overpass_query = f'''
            [out:xml][timeout:600];
            // Ireland bounding box
            way["highway"](51.3,-11.0,55.5,-5.0);
            (._;>;);
            out body;
            '''
    else:
        # Treat as a bounding box
        bbox = region.split(',')
        if len(bbox) != 4:
            logger.error(f"Invalid bounding box format: {region}")
            return None

        south, west, north, east = bbox
        if road_type:
            # Query filtered by road type
            overpass_query = f'''
            [out:xml][timeout:300];
            way["highway"="{road_type}"]({south},{west},{north},{east});
            (._;>;);
            out body;
            '''
        else:
            # Query for all highways in the bbox
            overpass_query = f'''
            [out:xml][timeout:300];
            way["highway"]({south},{west},{north},{east});
            (._;>;);
            out body;
            '''

    if road_type:
        output_path = output_dir / f"{region}_{road_type}.osm"
    else:
        output_path = output_dir / f"{region}_roads.osm"

    if region.count(',') == 3:  # It's a bbox
        output_path = output_dir / f"roads_{region.replace(',', '_')}.osm"

    # Force re-download by removing existing file
    if os.path.exists(output_path):
        logger.info(f"Removing existing OSM data file: {output_path}")
        os.remove(output_path)

    # Try each endpoint until one works
    for endpoint in overpass_endpoints:
        logger.info(f"Fetching OSM road data for {region} from {endpoint}")
        if road_type:
            logger.info(f"Filtering for road type: {road_type}")

        try:
            response = requests.post(
                endpoint,
                data={"data": overpass_query},
                timeout=600  # Increased timeout for larger dataset
            )
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                f.write(response.content)

            # Check if the response actually contains useful data
            file_size = os.path.getsize(output_path)
            if file_size < 300:  # If file is too small (just XML headers)
                logger.warning(f"Downloaded file is too small ({file_size} bytes). Likely no data returned.")
                continue  # Try next endpoint

            logger.info(f"Download complete: {output_path}")
            return output_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from {endpoint}: {e}")

    # If we get here, all endpoints failed or returned no data
    logger.error("All Overpass API endpoints failed or returned no data.")

    # Alternative 1: Use Geofabrik extract for Ireland
    logger.info("Trying to download Ireland extract from Geofabrik...")
    geofabrik_url = "https://download.geofabrik.de/europe/ireland-and-northern-ireland-latest.osm.pbf"
    geofabrik_output = output_dir / "ireland-latest.osm.pbf"

    try:
        response = requests.get(geofabrik_url, stream=True, timeout=600)
        response.raise_for_status()

        with open(geofabrik_output, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded Ireland extract: {geofabrik_output}")
        return geofabrik_output
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download from Geofabrik: {e}")

    # Alternative 2: Use a pre-defined OSM file with motorways for Ireland
    # Try downloading from a reliable direct source
    direct_sources = [
        "https://download.bbbike.org/osm/bbbike/Dublin/Dublin.osm.pbf",  # Dublin extract
        "https://download.bbbike.org/osm/bbbike/Ireland/Ireland.osm.pbf"  # Ireland extract
    ]

    for source_url in direct_sources:
        try:
            source_name = source_url.split('/')[-1]
            direct_output = output_dir / source_name
            logger.info(f"Trying to download from {source_url}")

            response = requests.get(source_url, stream=True, timeout=600)
            response.raise_for_status()

            with open(direct_output, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded extract: {direct_output}")
            return direct_output

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download from {source_url}: {e}")

    # If all attempts fail, return a fallback hardcoded bounding box
    logger.warning("All download attempts failed. Trying with a hardcoded Dublin bounding box...")
    return fetch_roads_overpass("53.25,-6.45,53.45,-6.05", road_type)  # Dublin area

def ensure_database_setup():
    """
    Ensures that the database and necessary tables exist.
    """
    # Update connection parameters to use the Docker service name
    conn_params = {
        'host': os.environ.get('COCKROACH_HOST', 'cockroachdb'),  # Use Docker service name
        'port': os.environ.get('COCKROACH_PORT', '26257'),
        'user': os.environ.get('COCKROACH_USER', 'root'),
        'password': os.environ.get('COCKROACH_PASSWORD', ''),
        'dbname': 'defaultdb',  # Connect to the default database first
        'sslmode': 'disable'  # For development environments
    }

    try:
        # Connect to default database first
        logger.info(f"Connecting to CockroachDB at {conn_params['host']}:{conn_params['port']}")
        conn = psycopg2.connect(**conn_params)
        conn.set_session(autocommit=True)  # Enable autocommit for database creation
        cursor = conn.cursor()

        # Check if the database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'booking'")
        if not cursor.fetchone():
            logger.info("Creating 'booking' database...")
            cursor.execute("CREATE DATABASE booking")
            logger.info("Database 'booking' created successfully")

        cursor.close()
        conn.close()

        # Now connect to the booking database to create tables
        conn_params['dbname'] = 'booking'
        conn = psycopg2.connect(**conn_params)
        conn.set_session(autocommit=True)
        cursor = conn.cursor()

        # Create the roads table if it doesn't exist
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS osm_roads (
            id BIGINT PRIMARY KEY,
            name TEXT,
            road_type TEXT,
            country TEXT,
            region TEXT,
            geometry TEXT,  -- GeoJSON as text
            tags JSONB
        )
        """)

        logger.info("Database tables checked/created")
        cursor.close()
        conn.close()

        return True
    except Exception as e:
        logger.error(f"Database setup error: {e}")
        return False

def import_osm_roads(osm_file, filter_road_type=None):
    """Import roads from OSM file into database, optionally filtering by road type"""
    logger.info(f"Importing roads from {osm_file}")
    if filter_road_type:
        logger.info(f"Filtering for road type: {filter_road_type}")

    # Check if the file exists and has content
    file_path = Path(osm_file)
    if not file_path.exists():
        logger.error(f"OSM file {osm_file} does not exist!")
        return

    file_size = file_path.stat().st_size
    if file_size == 0:
        logger.error(f"OSM file {osm_file} is empty!")
        return

    logger.info(f"OSM file size: {file_size} bytes")

    # Enable debug logging
    logger.setLevel(logging.DEBUG)

    try:
        # First try with osmium
        logger.info("Attempting import using osmium handler...")
        handler = RoadHandler(cockroach_conn, filter_road_type)
        handler.apply_file(str(osm_file))
        handler.finalize()

        # If no roads processed, try fallback method
        if handler.road_count == 0:
            logger.warning(f"No roads processed with osmium handler. Trying fallback XML parsing...")
            fallback_import_roads(osm_file, filter_road_type)
    except Exception as e:
        logger.error(f"Error with osmium import: {e}")
        logger.warning("Trying fallback import method...")
        fallback_import_roads(osm_file, filter_road_type)

    # Restore normal logging
    logger.setLevel(logging.INFO)
    logger.info(f"Import completed for {osm_file}")

def fallback_import_roads(osm_file, filter_road_type=None):
    """Fallback method to import roads using direct XML parsing"""
    logger.info("Using fallback XML parsing method for OSM import")
    if filter_road_type:
        logger.info(f"Filtering for road type: {filter_road_type}")

    try:
        # Parse OSM XML file
        nodes = {}  # Dictionary to store node coordinates
        ways = []   # List to store way elements

        # Process the XML in chunks to handle large files
        logger.info("Parsing OSM XML file...")

        # First collect all nodes
        context = ET.iterparse(osm_file, events=('start', 'end'))
        for event, elem in context:
            if event == 'end' and elem.tag == 'node':
                try:
                    node_id = int(elem.attrib['id'])
                    lat = float(elem.attrib['lat'])
                    lon = float(elem.attrib['lon'])
                    nodes[node_id] = (lon, lat)

                    # Log progress periodically
                    if len(nodes) % 100000 == 0:
                        logger.info(f"Parsed {len(nodes)} nodes")

                except (KeyError, ValueError) as e:
                    logger.debug(f"Error parsing node: {e}")

                # Clear the element to save memory
                elem.clear()

            # Collect highways
            elif event == 'end' and elem.tag == 'way':
                try:
                    is_highway = False
                    for tag in elem.findall('tag'):
                        if tag.attrib.get('k') == 'highway':
                            is_highway = True
                            break

                    if is_highway:
                        ways.append(elem)
                        # Don't clear highway elements as we need them
                    else:
                        elem.clear()

                    # Log progress periodically
                    if len(ways) % 1000 == 0:
                        logger.info(f"Found {len(ways)} highways")
                except Exception as e:
                    logger.debug(f"Error processing way element: {e}")
                    elem.clear()

        logger.info(f"Parsed {len(nodes)} nodes and found {len(ways)} highways")

        # Group ways by name
        road_groups = defaultdict(list)

        logger.info("Processing highways...")
        for way in ways:
            try:
                way_id = int(way.attrib['id'])

                # Extract tags
                tags = {}
                name = None
                road_type = None
                country = None
                region = None

                for tag in way.findall('tag'):
                    k = tag.attrib.get('k')
                    v = tag.attrib.get('v')
                    tags[k] = v

                    if k == 'name':
                        name = v
                    elif k == 'highway':
                        road_type = v
                    elif k == 'addr:country':
                        country = v
                    elif k == 'addr:region' or k == 'addr:state':
                        region = v

                # Skip if not the desired road type
                if filter_road_type and road_type != filter_road_type:
                    continue

                # Get node references
                node_refs = []
                for nd in way.findall('nd'):
                    try:
                        ref = int(nd.attrib['ref'])
                        node_refs.append(ref)
                    except (KeyError, ValueError):
                        pass

                # Create geometry if we have enough nodes
                if len(node_refs) >= 2:
                    # Get coordinates for each node reference
                    coords = []
                    for ref in node_refs:
                        if ref in nodes:
                            coords.append(nodes[ref])

                    # Create linestring if we have enough coordinates
                    if len(coords) >= 2:
                        try:
                            line = LineString(coords)
                            geojson = mapping(line)

                            # Group by name
                            group_key = name if name else f"unnamed_road_{way_id}"
                            road_groups[group_key].append({
                                'id': way_id,
                                'name': name,
                                'road_type': road_type,
                                'country': country,
                                'region': region,
                                'geometry': geojson,
                                'tags': tags
                            })
                        except Exception as e:
                            logger.debug(f"Error creating geometry for way {way_id}: {e}")
            except Exception as e:
                logger.debug(f"Error processing way: {e}")

        # Now merge roads with the same name and insert into database
        conn = cockroach_conn
        cursor = conn.cursor()

        road_count = 0
        batch = []
        batch_size = 1000

        logger.info(f"Merging {len(road_groups)} named road groups...")
        merged_count = 0

        for name, roads in road_groups.items():
            try:
                if len(roads) == 1:
                    # No need to merge if only one segment
                    road = roads[0]
                    batch.append({
                        'id': road['id'],
                        'name': road['name'],
                        'road_type': road['road_type'],
                        'country': road['country'],
                        'region': road['region'],
                        'geometry': json.dumps(road['geometry']),
                        'tags': json.dumps(road['tags'])
                    })
                else:
                    # Need to merge multiple segments
                    # Use the first road's metadata as base
                    base_road = roads[0]

                    # Create list of linestrings to merge
                    lines = []
                    for road in roads:
                        # Convert GeoJSON geometry to LineString object
                        coords = road['geometry']['coordinates']
                        if coords:
                            line = LineString(coords)
                            if not line.is_empty:
                                lines.append(line)

                    if lines:
                        # Try to merge lines into a single linestring
                        try:
                            # First attempt: linemerge for connected lines
                            merged_line = linemerge(lines)

                            # If result is still a MultiLineString, keep it as such
                            if isinstance(merged_line, MultiLineString):
                                logger.debug(f"Created MultiLineString for {name} with {len(merged_line.geoms)} parts")
                            else:
                                logger.debug(f"Successfully merged {len(lines)} segments into single line for {name}")

                            merged_geojson = json.dumps(mapping(merged_line))

                            # Add merged road to batch
                            batch.append({
                                'id': base_road['id'],  # Use the first road's ID
                                'name': name,
                                'road_type': base_road['road_type'],
                                'country': base_road['country'],
                                'region': base_road['region'],
                                'geometry': merged_geojson,
                                'tags': json.dumps(base_road['tags'])
                            })

                            merged_count += 1
                        except Exception as e:
                            logger.error(f"Error merging lines for {name}: {e}")
                            # Fallback: add roads individually
                            for road in roads:
                                batch.append({
                                    'id': road['id'],
                                    'name': road['name'],
                                    'road_type': road['road_type'],
                                    'country': road['country'],
                                    'region': road['region'],
                                    'geometry': json.dumps(road['geometry']),
                                    'tags': json.dumps(road['tags'])
                                })

                road_count += 1

                # Insert batch if reached batch size
                if len(batch) >= batch_size:
                    _insert_batch(conn, cursor, batch)
                    batch = []
                    logger.info(f"Processed {road_count} road groups")

            except Exception as e:
                logger.error(f"Error processing road group {name}: {e}")

        # Insert any remaining roads
        if batch:
            _insert_batch(conn, cursor, batch)

        logger.info(f"Fallback import completed: {road_count} road groups processed, {merged_count} merged")

    except Exception as e:
        logger.error(f"Error in fallback import: {e}")
        raise

def _insert_batch(conn, cursor, batch):
    """Helper function to insert a batch of roads"""
    if not batch:
        return

    try:
        args = []
        for road in batch:
            args.append((
                road['id'],
                road['name'],
                road['road_type'],
                road['country'],
                road['region'],
                road['geometry'],
                road['tags']
            ))

        cursor.executemany(
            """
            INSERT INTO osm_roads
            (id, name, road_type, country, region, geometry, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            road_type = EXCLUDED.road_type,
            country = EXCLUDED.country,
            region = EXCLUDED.region,
            geometry = EXCLUDED.geometry,
            tags = EXCLUDED.tags
            """,
            args
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Error inserting batch: {e}")

def main():
    """Main function to download and import OSM road data"""
    # Ensure database is set up before proceeding
    if not ensure_database_setup():
        logger.error("Failed to set up database. Exiting.")
        return

    # Download only motorways for all of Ireland
    region = "ireland"

    # Try multiple road types if needed
    road_types = ["motorway", "trunk"]  # In Ireland, some major roads are tagged as "trunk"

    for road_type in road_types:
        logger.info(f"Attempting to download and import {road_type} roads for Ireland")
        # Download the data
        osm_file = fetch_roads_overpass(region, road_type)
        if osm_file:
            import_osm_roads(osm_file, road_type)  # Pass the road type filter

            # Check if we've successfully imported roads
            conn = cockroach_conn
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM osm_roads WHERE road_type = '{road_type}'")
            count = cursor.fetchone()[0]

            if count > 0:
                logger.info(f"Successfully imported {count} {road_type} roads")
            else:
                logger.warning(f"No {road_type} roads were imported")

if __name__ == "__main__":
    main()