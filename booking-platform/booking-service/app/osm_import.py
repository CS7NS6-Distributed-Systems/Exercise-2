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
from app.db import get_cockroach_connection, release_cockroach_connection
import io

# Configure logging - set to debug level to see more information
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set up a debug flag to use during development
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'False').lower() == 'true'


# WKB helper with more permissive settings
wkb_factory = osmium.geom.WKBFactory()
class RoadHandler(osmium.SimpleHandler):
    def __init__(self, db_connection):
        super(RoadHandler, self).__init__()
        self.conn = db_connection
        self.cursor = self.conn.cursor()
        self.batch_size = 1000
        self.total_ways = 0
        self.skipped_ways = 0
        self.highways_found = 0
        self.node_count = 0
        self.node_cache = {}  # Cache to store node coordinates

        # Dictionaries to hold roads by key and their segments
        self.road_groups = defaultdict(list)  # Maps logical road key to list of segments
        self.region_ids = {}  # Maps region name to database ID

        # Define which highway types to include
        self.highway_types = {
            'motorway'
        }

        # Track stats for reporting
        self.road_count = 0
        self.segment_count = 0

    # Add a node method to collect node coordinates
    def node(self, n):
        self.node_count += 1
        # Store node coordinates in cache
        self.node_cache[n.id] = (n.location.lon, n.location.lat)
        if self.node_count % 100000 == 0:
            logger.info(f"Processed {self.node_count} nodes")

    def way(self, w):
        self.total_ways += 1

        try:
            # Check if it's a road/highway
            if 'highway' not in w.tags:
                if self.total_ways % 1000 == 0:
                    logger.debug(f"Processed {self.total_ways} ways, {self.highways_found} highways found, {self.skipped_ways} skipped")
                return

            # Filter for specific highway types
            highway_type = None
            for tag in w.tags:
                if tag.k == 'highway':
                    highway_type = tag.v
                    break

            # Skip if not in our list of highway types
            if highway_type not in self.highway_types:
                self.skipped_ways += 1
                return

            self.highways_found += 1

            # Extract tags for this way
            tags = {tag.k: tag.v for tag in w.tags}

            # Determine country and region
            country = tags.get('addr:country', 'Ireland')  # Default to Ireland
            region = tags.get('addr:region') or tags.get('addr:state', 'Unknown')

            # Get or create region ID
            region_key = f"{region}, {country}"
            if region_key not in self.region_ids:
                # Check if region exists
                self.cursor.execute(
                    "SELECT id FROM regions WHERE name = %s AND country = %s",
                    (region, country)
                )
                result = self.cursor.fetchone()

                if result:
                    self.region_ids[region_key] = result[0]
                else:
                    # Insert new region
                    self.cursor.execute(
                        "INSERT INTO regions (name, country) VALUES (%s, %s) RETURNING id",
                        (region, country)
                    )
                    self.region_ids[region_key] = self.cursor.fetchone()[0]
                    self.conn.commit()

            region_id = self.region_ids[region_key]

            # Create the geometry
            geometry = self._create_geometry(w)
            if not geometry:
                self.skipped_ways += 1
                return

            line, geojson = geometry

            # Calculate road length in meters
            length_meters = line.length * 111000  # Rough conversion from degrees to meters

            # Generate logical road key for grouping
            # Use a more sophisticated approach to group highways
            road_key = self._get_road_key(tags, w.id)

            # Create segment data
            segment = {
                'osm_way_id': w.id,
                'geometry': geojson,
                'length_meters': length_meters,
                'start_node_id': w.nodes[0].ref if len(w.nodes) > 0 else None,
                'end_node_id': w.nodes[-1].ref if len(w.nodes) > 0 else None,
                'tags': tags,
                'road_type': highway_type,
                'country': country,
                'region_id': region_id,
                'line': line  # Store line object for possible merging
            }

            # Add segment to appropriate road group
            self.road_groups[road_key].append(segment)

        except Exception as e:
            logger.error(f"Error processing way {w.id}: {e}")
            self.skipped_ways += 1

    def _get_road_key(self, tags, way_id):
        """
        Generates a logical key for grouping road segments.
        Prioritizes:
        1. ref tag (M1, M4, etc.)
        2. route number
        3. name
        4. road_number
        """
        # For motorways, the ref is the most important identifier
        if 'ref' in tags:
            ref = tags['ref'].strip()
            # For motorways with directional info
            direction = tags.get('carriageway_ref', '').strip().upper()
            if direction:
                return f"REF:{ref}:{direction}"
            return f"REF:{ref}"

        # Try using name if available
        if 'name' in tags and tags['name']:
            return f"NAME:{tags['name']}"

        # For routes
        if 'route' in tags and 'route_number' in tags:
            return f"ROUTE:{tags['route']}:{tags['route_number']}"

        # If we get here, use any highway identifier we can find
        for key in ['nat_ref', 'int_ref', 'network']:
            if key in tags and tags[key]:
                return f"{key.upper()}:{tags[key]}"

        # Last resort - use the way ID with a prefix
        return f"UNNAMED_HIGHWAY:{way_id}"

    def _create_geometry(self, w):
        """Creates a geometry from a way, returning (line, geojson) or None if failed"""
        wkb = None

        try:
            # First approach: Standard OSM linestring creation
            if any(node.location.valid() for node in w.nodes):
                wkb = wkb_factory.create_linestring(w)
        except Exception as e:
            logger.debug(f"Standard linestring creation failed for way {w.id}: {e}")

        # If standard approach failed, try with node cache
        if wkb is None:
            try:
                coords = []
                for node in w.nodes:
                    if node.ref in self.node_cache:
                        coords.append(self.node_cache[node.ref])

                if len(coords) >= 2:
                    line = LineString(coords)
                    geojson = json.dumps(mapping(line))
                    return (line, geojson)
                else:
                    logger.debug(f"Not enough cached coordinates for way {w.id}: {len(coords)} points")
                    return None
            except Exception as e:
                logger.debug(f"Manual linestring creation failed for way {w.id}: {e}")
                return None
        else:
            # Process WKB from standard approach
            try:
                line = wkblib.loads(wkb, hex=True)
                if not line.is_empty:
                    geojson = json.dumps(mapping(line))
                    return (line, geojson)
                else:
                    logger.debug(f"Empty linestring for way {w.id}")
                    return None
            except Exception as e:
                logger.debug(f"Error processing WKB for way {w.id}: {e}")
                return None

    def finalize(self):
        """
        Process all collected road groups and create roads and segments in the database.
        This runs after all ways have been processed.
        """
        logger.info(f"Finalizing import: Creating roads from {len(self.road_groups)} groups")

        # Process each road group
        for road_key, segments in self.road_groups.items():
            try:
                # Use first segment for basic road properties
                first_segment = segments[0]

                # Generate a proper road name based on the segment tags
                road_name = autofill_road_name_from_tags(first_segment['tags'])

                # Use the first segment's OSM ID as the road OSM ID
                road_osm_id = first_segment['osm_way_id']

                # Insert the road
                self.cursor.execute(
                    """
                    INSERT INTO roads
                    (osm_id, name, road_type, country, region_id, tags)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (osm_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    road_type = EXCLUDED.road_type,
                    country = EXCLUDED.country,
                    region_id = EXCLUDED.region_id,
                    tags = EXCLUDED.tags
                    RETURNING id
                    """,
                    (
                        road_osm_id,
                        road_name,
                        first_segment['road_type'],
                        first_segment['country'],
                        first_segment['region_id'],
                        json.dumps(first_segment['tags'])
                    )
                )
                road_id = self.cursor.fetchone()[0]
                self.conn.commit()
                self.road_count += 1

                # Insert all segments for this road
                for segment in segments:
                    self.cursor.execute(
                        """
                        INSERT INTO road_segments
                        (road_id, osm_way_id, geometry, length_meters, start_node_id, end_node_id, tags)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (osm_way_id) DO UPDATE SET
                        road_id = EXCLUDED.road_id,
                        geometry = EXCLUDED.geometry,
                        length_meters = EXCLUDED.length_meters,
                        start_node_id = EXCLUDED.start_node_id,
                        end_node_id = EXCLUDED.end_node_id,
                        tags = EXCLUDED.tags
                        """,
                        (
                            road_id,
                            segment['osm_way_id'],
                            segment['geometry'],
                            segment['length_meters'],
                            segment['start_node_id'],
                            segment['end_node_id'],
                            json.dumps(segment['tags'])
                        )
                    )
                    self.segment_count += 1

                self.conn.commit()

                if self.road_count % 10 == 0:
                    logger.info(f"Created {self.road_count} roads with {self.segment_count} segments")

            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error finalizing road group {road_key}: {e}")

        logger.info(f"Total ways examined: {self.total_ways}")
        logger.info(f"Total highways found: {self.highways_found}")
        logger.info(f"Total ways skipped: {self.skipped_ways}")
        logger.info(f"Total logical roads created: {self.road_count}")
        logger.info(f"Total road segments created: {self.segment_count}")
        logger.info(f"Average segments per road: {self.segment_count / self.road_count if self.road_count else 0:.2f}")
def fetch_roads_overpass(region="ireland"):
    """
    Fetches toll road data from Overpass API for a region.

    Args:
        region: A string representing the region ("ireland" by default)

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

    # Build the query specifically for toll roads
    if region.lower() == "ireland":
        # For Ireland, use a more direct name-based approach with wide area
        overpass_query = f'''
        [out:xml][timeout:600];
        // Ireland bounding box with toll roads
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
        overpass_query = f'''
        [out:xml][timeout:300];
        way["highway"]({south},{west},{north},{east});
        (._;>;);
        out body;
        '''

    output_path = output_dir / f"{region}_toll_roads.osm"

    # Force re-download by removing existing file
    if os.path.exists(output_path):
        logger.info(f"Removing existing toll roads OSM data file: {output_path}")
        os.remove(output_path)

    # Try each endpoint until one works
    for endpoint in overpass_endpoints:
        logger.info(f"Fetching toll road data for {region} from {endpoint}")

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

    # Try with a broader query to include any road with toll tag
    for endpoint in overpass_endpoints:
        logger.info(f"Trying broader toll road query for {region} from {endpoint}")

        overpass_query = f'''
        [out:xml][timeout:600];
        // Ireland bounding box with toll roads (alternative query)
        way["highway"](51.3,-11.0,55.5,-5.0);
        (._;>;);
        out body;
        '''

        try:
            response = requests.post(
                endpoint,
                data={"data": overpass_query},
                timeout=600
            )
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                f.write(response.content)

            file_size = os.path.getsize(output_path)
            if file_size < 300:
                logger.warning(f"Downloaded file is too small ({file_size} bytes). Likely no data returned.")
                continue

            logger.info(f"Download complete with alternative query: {output_path}")
            return output_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch data from {endpoint}: {e}")

    # If still failing, return a fallback Dublin area
    logger.warning("All download attempts failed. Trying with a hardcoded Dublin area...")
    return fetch_roads_overpass("53.25,-6.45,53.45,-6.05")  # Dublin area

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


        logger.info("Database tables checked/created")
        cursor.close()
        conn.close()

        return True
    except Exception as e:
        logger.error(f"Database setup error: {e}")
        return False

def import_osm_roads(osm_file):
    """Import toll roads from OSM file into database"""
    logger.info(f"Importing toll roads from {osm_file}")

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
        # Import using osmium
        logger.info("Importing toll roads using osmium handler...")
        handler = RoadHandler(get_cockroach_connection())
        handler.apply_file(str(osm_file))
        handler.finalize()
    except Exception as e:
        logger.error(f"Error with osmium import: {e}")

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
        conn = get_cockroach_connection()
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
def autofill_road_name_from_tags(tags):
    """
    Autofills a road name from OpenStreetMap-like tags, aiming for uniqueness.

    Prioritizes:
    1. 'name' tag (if present)
    2. 'ref' tag (e.g., "M4", "M6") - with carriageway differentiation if applicable
    3. 'nat_ref' tag (e.g., "T7", "T3")
    4. 'int_ref' tag (e.g., "E 01")

    If none of these are found, returns a generic "Unnamed Road".

    Always appends carriageway information if 'carriageway_ref' tag is present
    to distinguish between carriageways (e.g., "M4 (E)" or "Main Street (N)").

    Args:
        tags (dict): Dictionary of road tags.

    Returns:
        str: Autogenerated road name, aiming for uniqueness.
    """
    if not tags:
        return "Unnamed Road"  # Handle case with no tags

    # Determine the base name from available tags
    base_name = None

    if "name" in tags and tags["name"]:
        base_name = tags["name"]  # Use 'name' if available
    elif "ref" in tags and tags["ref"]:
        base_name = tags["ref"]  # Use 'ref' as primary fallback
    elif "nat_ref" in tags and tags["nat_ref"]:
        base_name = tags["nat_ref"]  # Use 'nat_ref' if 'ref' is missing
    elif "int_ref" in tags and tags["int_ref"]:
        # For int_ref, might have multiple refs like "E 01;E 16". Use the first one.
        int_refs = tags["int_ref"].split(';')
        if int_refs:
            base_name = int_refs[0].strip()  # Use the first int_ref, strip whitespace

    # If we couldn't find a base name, use a generic one
    if not base_name:
        road_type = tags.get("highway", "road")  # Try to get road type, default to "road"
        base_name = f"Unnamed {road_type.capitalize()}"

    # Always add carriageway reference in brackets if available
    if "carriageway_ref" in tags and tags["carriageway_ref"]:
        carriageway_ref = tags["carriageway_ref"].strip().upper()  # E, W, S, N
        return f"{base_name} ({carriageway_ref})"

    return base_name

def autofill_mising_names():
    # select all the roads with missing names
    conn = get_cockroach_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, tags FROM roads WHERE name IS NULL")
    rows = cursor.fetchall()
    for row in rows:
        id = row[0]
        tags = row[1]
        name = autofill_road_name_from_tags(tags)
        cursor.execute("UPDATE roads SET name = %s WHERE id = %s", (name, id))
    conn.commit()
def main():
    """Main function to import OSM road data from local file"""
    # Ensure database is set up before proceeding
    if not ensure_database_setup():
        logger.error("Failed to set up database. Exiting.")
        return

    # Path to your local OSM PBF file - adjust this path as needed
    osm_file = "./osm_data/ireland-and-northern-ireland-latest.osm.pbf"

    logger.info(f"Importing road data from local file: {osm_file}")

    # Check if the file exists
    if not os.path.exists(osm_file):
        logger.error(f"OSM file {osm_file} does not exist!")
        return

    # Import the data
    import_osm_roads(osm_file)

    # autofill_mising_names()

    # Check if we've successfully imported roads
    conn = get_cockroach_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM roads")
        road_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM road_segments")
        segment_count = cursor.fetchone()[0]

        if road_count > 0:
            logger.info(f"Successfully imported {road_count} roads with {segment_count} segments")
        else:
            logger.warning("No roads were imported")
    except Exception as e:
        logger.error(f"Error checking imported data: {e}")
    finally:
        release_cockroach_connection(conn)

if __name__ == "__main__":
    main()