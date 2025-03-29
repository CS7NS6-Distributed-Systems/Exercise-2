// Global variables for modals and authentication
      let deleteItemId = null;
      let deleteItemType = null;
      const deleteModal = new bootstrap.Modal(document.getElementById('delete-modal'));
      const roadModal = new bootstrap.Modal(document.getElementById('road-modal'));
      const viewRoadModal = new bootstrap.Modal(document.getElementById('view-road-modal'));
      const slotModal = new bootstrap.Modal(document.getElementById('slot-modal'));
      const viewSlotModal = new bootstrap.Modal(document.getElementById('view-slot-modal'));
      const viewBookingModal = new bootstrap.Modal(document.getElementById('view-booking-modal'));

      // Global variables for pagination
      // Slots pagination (already exists)
      let currentSlotsPage = 1;
      let slotItemsPerPage = 20;
      let totalSlotItems = 0;
      let totalSlotPages = 0;

      // Roads pagination
      let currentRoadsPage = 1;
      let roadItemsPerPage = 20;
      let totalRoadItems = 0;
      let totalRoadPages = 0;

      // Bookings pagination
      let currentBookingsPage = 1;
      let bookingItemsPerPage = 20;
      let totalBookingItems = 0;
      let totalBookingPages = 0;

      // Get authentication token from localStorage
      const token = localStorage.getItem('accessToken');

      // Check if user is authenticated
      if (!token) {
          // Redirect to login page if no token found
          alert('Please login to access dashboard');
          window.location.href = '/static/user.html';
      }

      // Helper function to make authenticated API requests
      async function fetchWithAuth(url, options = {}) {
          // Ensure headers object exists
          if (!options.headers) {
              options.headers = {};
          }

          // Add authorization header
          options.headers['Authorization'] = `Bearer ${token}`;

          try {
              const response = await fetch(url, options);

              // If unauthorized (token expired or invalid), redirect to login
              if (response.status === 401) {
                  localStorage.removeItem('accessToken');
                  alert('Your session has expired. Please login again.');
                  window.location.href = '/static/user.html';
                  return null;
              }

              return response;
          } catch (error) {
              console.error('API request failed:', error);
              throw error;
          }
      }

      // Initialize the active section based on URL hash or default to dashboard
      document.addEventListener('DOMContentLoaded', function() {
          const hash = window.location.hash.substring(1) || 'dashboard-section';
          activateSection(hash);
          loadDashboardData();

          // Set up section navigation
          document.querySelectorAll('.section-link').forEach(link => {
              link.addEventListener('click', function(e) {
                  e.preventDefault();
                  const sectionId = this.getAttribute('data-section');
                  activateSection(sectionId);

                  // Load data for the section
                  if (sectionId === 'roads-section') {
                      loadRoads();
                  } else if (sectionId === 'booking-slots-section') {
                      loadBookingSlots();
                      loadRoadsForDropdown();
                  } else if (sectionId === 'bookings-section') {
                      loadBookings();
                  } else if (sectionId === 'dashboard-section') {
                      loadDashboardData();
                  }
              });
          });

          document.getElementById('save-road-btn').addEventListener('click', saveRoad);

          document.getElementById('save-slot-btn').addEventListener('click', saveBookingSlot);

          // Set up delete confirmation
          document.getElementById('confirm-delete-btn').addEventListener('click', confirmDelete);

          // Set up pagination events for roads
          document.getElementById('roads-per-page').addEventListener('change', function(e) {
              roadItemsPerPage = parseInt(e.target.value);
              currentRoadsPage = 1; // Reset to first page when changing items per page
              loadRoads();
          });

          // Set up pagination events for slots (rename existing variables to match naming convention)
          document.getElementById('slots-per-page').addEventListener('change', function(e) {
              slotItemsPerPage = parseInt(e.target.value);
              currentSlotsPage = 1; // Reset to first page when changing items per page
              loadBookingSlots();
          });

          // Set up pagination events for bookings
          document.getElementById('bookings-per-page').addEventListener('change', function(e) {
              bookingItemsPerPage = parseInt(e.target.value);
              currentBookingsPage = 1; // Reset to first page when changing items per page
              loadBookings();
          });

          // Initial data load based on the current section
          if (hash === 'roads-section') {
              loadRoads();
          } else if (hash === 'booking-slots-section') {
              loadBookingSlots();
              loadRoadsForDropdown();
          } else if (hash === 'bookings-section') {
              loadBookings();
          }

          // Force regenerate all pagination UIs on first load
          setTimeout(() => {
              console.log("Forcing pagination regeneration");
              if (document.getElementById('roads-section').classList.contains('active-section')) {
                  updateRoadsPagination();
              }
              if (document.getElementById('booking-slots-section').classList.contains('active-section')) {
                  updateSlotsPagination();
              }
              if (document.getElementById('bookings-section').classList.contains('active-section')) {
                  updateBookingsPagination();
              }
          }, 1000);
      });

      function activateSection(sectionId) {
          // Hide all sections
          document.querySelectorAll('.content-section').forEach(section => {
              section.classList.remove('active-section');
          });

          // Show the selected section
          const selectedSection = document.getElementById(sectionId);
          if (selectedSection) {
              selectedSection.classList.add('active-section');

              // Update navigation active state
              document.querySelectorAll('.section-link').forEach(link => {
                  link.classList.remove('active');
                  if (link.getAttribute('data-section') === sectionId) {
                      link.classList.add('active');
                  }
              });

              // Update URL hash
              window.location.hash = sectionId;
          }
      }

      // Dashboard data loading
      function loadDashboardData() {
          // Load summary counts
          fetchWithAuth('/admin/stats')
              .then(response => response.json())
              .then(data => {
                  document.getElementById('total-roads').textContent = data.total_roads || 0;
                  document.getElementById('total-slots').textContent = data.total_slots || 0;
                  document.getElementById('total-bookings').textContent = data.total_bookings || 0;
                  document.getElementById('total-users').textContent = data.total_users || 0;
              })
              .catch(error => console.error('Error loading dashboard stats:', error));

          // Load recent bookings
          fetchWithAuth('/admin/bookings?limit=5')
              .then(response => response.json())
              .then(data => {
                  const bookings = Array.isArray(data) ? data : (data.bookings || []);
                  const tableBody = document.querySelector('#recent-bookings-table tbody');
                  tableBody.innerHTML = '';

                  if (bookings.length === 0) {
                      tableBody.innerHTML = '<tr><td colspan="6" class="text-center">No bookings found</td></tr>';
                      return;
                  }

                  bookings.forEach(booking => {
                      const row = document.createElement('tr');
                      row.innerHTML = `
                          <td>${booking.booking_id.substring(0, 8)}...</td>
                          <td>${booking.username}</td>
                          <td>${booking.origin || 'N/A'}</td>
                          <td>${booking.destination || 'N/A'}</td>
                          <td>${booking.lines_count || 0}</td>
                          <td>${new Date(booking.booking_timestamp).toLocaleString()}</td>
                      `;
                      tableBody.appendChild(row);
                  });
              })
              .catch(error => console.error('Error loading recent bookings:', error));
      }

      // Roads data loading and actions
  function loadRoads() {
    // Build URL with pagination parameters
    const url = `/admin/roads?page=${currentRoadsPage}&per_page=${roadItemsPerPage}`;

    console.log(`Loading roads with page=${currentRoadsPage}, items per page=${roadItemsPerPage}`);

    fetchWithAuth(url)
        .then(response => {
            // Extract pagination information from headers if available
            const totalCountHeader = response.headers.get('X-Total-Count');
            if (totalCountHeader) {
                totalRoadItems = parseInt(totalCountHeader);
                totalRoadPages = Math.ceil(totalRoadItems / roadItemsPerPage);
                console.log(`Header pagination info: ${totalRoadItems} items, ${totalRoadPages} pages`);
            }
            return response.json();
        })
        .then(data => {
            // Check if data is an object with 'roads' property (API might return {roads: [...]} format)
            const roads = Array.isArray(data) ? data : (data.roads || []);

            // If we have pagination metadata in the response
            if (data.pagination) {
                totalRoadItems = data.pagination.total_items || totalRoadItems;
                totalRoadPages = data.pagination.total_pages || totalRoadPages;
                currentRoadsPage = data.pagination.current_page || currentRoadsPage;
                console.log(`Response pagination info: ${totalRoadItems} items, ${totalRoadPages} pages, current page ${currentRoadsPage}`);
            }

            // If no pagination info provided, estimate it from the data we have
            if (totalRoadItems === 0) {
                // Check if we got a full page of results
                if (roads.length >= roadItemsPerPage) {
                    // We don't know the total, but there's at least one more page
                    // Let's assume there's at least one more page
                    totalRoadItems = currentRoadsPage * roadItemsPerPage + roadItemsPerPage;
                    totalRoadPages = currentRoadsPage + 1;
                } else if (roads.length > 0) {
                    // This is likely the last page with partial results
                    totalRoadItems = (currentRoadsPage - 1) * roadItemsPerPage + roads.length;
                    totalRoadPages = currentRoadsPage;
                    // If we're on page 1, the total is just what we have
                    if (currentRoadsPage === 1) {
                        totalRoadItems = roads.length;
                        totalRoadPages = 1;
                    }
                }

                // If we're showing 20 items and got 20 items, then assume there are at least 40 total
                // (This is a fallback estimate to ensure we show pagination)
                if (currentRoadsPage === 1 && roads.length === roadItemsPerPage) {
                    totalRoadItems = roadItemsPerPage * 2; // Assume at least 2 pages
                    totalRoadPages = 2;
                }

                console.log(`Estimated pagination: ${totalRoadItems} items, ${totalRoadPages} pages`);
            }

            // If we still don't have a total but have items, force some sensible defaults
            if (totalRoadPages === 0 && roads.length > 0) {
                // Force at least 2 pages if we have a full page of results
                if (roads.length >= roadItemsPerPage) {
                    totalRoadPages = 2;
                    totalRoadItems = roadItemsPerPage * 2;
                } else {
                    totalRoadPages = 1;
                    totalRoadItems = roads.length;
                }
                console.log(`Forced pagination: ${totalRoadItems} items, ${totalRoadPages} pages`);
            }

            console.log(`Loaded ${roads.length} roads. Total: ${totalRoadItems}, Pages: ${totalRoadPages}`); // Debug logging

            const tableBody = document.querySelector('#roads-table tbody');
            tableBody.innerHTML = '';

            if (roads.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No roads found</td></tr>';
                return;
            }

            roads.forEach(road => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${road.id.substring(0, 8)}...</td>
                    <td>${road.name || 'Unnamed'}</td>
                    <td>${road.road_type || 'N/A'}</td>
                    <td>${road.country || 'N/A'}</td>
                    <td>${road.region_name || 'N/A'}</td>
                    <td>${road.hourly_capacity}</td>
                    <td>
                        <button class="btn btn-sm btn-info view-road" data-id="${road.id}">View</button>
                        <button class="btn btn-sm btn-warning edit-road" data-id="${road.id}">Edit</button>
                        <button class="btn btn-sm btn-danger delete-road" data-id="${road.id}">Delete</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });

            // Add event listeners for the action buttons
            document.querySelectorAll('.view-road').forEach(btn => {
                btn.addEventListener('click', () => viewRoad(btn.getAttribute('data-id')));
            });

            document.querySelectorAll('.edit-road').forEach(btn => {
                btn.addEventListener('click', () => editRoad(btn.getAttribute('data-id')));
            });

            document.querySelectorAll('.delete-road').forEach(btn => {
                btn.addEventListener('click', () => {
                    deleteItemId = btn.getAttribute('data-id');
                    deleteItemType = 'road';
                    deleteModal.show();
                });
            });

            // Update pagination UI
            console.log(`Final pagination values: page ${currentRoadsPage}/${totalRoadPages}, ${totalRoadItems} total items`);
            updateRoadsPagination();
        })
        .catch(error => {
            console.error('Error loading roads:', error);
            const tableBody = document.querySelector('#roads-table tbody');
            tableBody.innerHTML = `<tr><td colspan="7" class="text-center text-danger">Failed to load roads: ${error.message}</td></tr>`;
        });
}

      function viewRoad(roadId) {
          fetchWithAuth(`/admin/roads/${roadId}`)
              .then(response => response.json())
              .then(road => {
                  // Store road ID in a hidden element for reference
                  if (!document.getElementById('view-road-id')) {
                      const hiddenId = document.createElement('span');
                      hiddenId.id = 'view-road-id';
                      hiddenId.style.display = 'none';
                      document.getElementById('view-road-modal').querySelector('.modal-body').appendChild(hiddenId);
                  }
                  document.getElementById('view-road-id').setAttribute('data-id', road.id);

                  document.getElementById('view-road-name').textContent = road.name || 'Unnamed';
                  document.getElementById('view-road-type').textContent = road.road_type || 'N/A';
                  document.getElementById('view-road-country').textContent = road.country || 'N/A';
                  document.getElementById('view-road-region').textContent = road.region_name || 'N/A';
                  document.getElementById('view-road-capacity').textContent = road.hourly_capacity;
                  document.getElementById('view-road-created').textContent =
                      road.created_at ? new Date(road.created_at).toLocaleString() : 'N/A';

                  // Display segments if available
                  const segmentsList = document.getElementById('road-segments-list');
                  segmentsList.innerHTML = '';

                  if (road.segments && road.segments.length > 0) {
                      road.segments.forEach(segment => {
                          const segmentItem = document.createElement('a');
                          segmentItem.href = '#';
                          segmentItem.classList.add('list-group-item', 'list-group-item-action');
                          segmentItem.innerHTML = `
                              Segment: ${segment.segment_id.substring(0, 8)}...
                              <span class="badge bg-secondary float-end">${segment.length_meters ? segment.length_meters.toFixed(1) + 'm' : 'N/A'}</span>
                          `;
                          segmentItem.addEventListener('click', (e) => {
                              e.preventDefault();
                              viewRoadSegment(segment.segment_id);
                          });
                          segmentsList.appendChild(segmentItem);
                      });
                  } else {
                      segmentsList.innerHTML = '<div class="text-center p-3">No segments available</div>';
                  }

                  viewRoadModal.show();
              })
              .catch(error => console.error('Error loading road details:', error));
      }

      function editRoad(roadId) {
          fetchWithAuth(`/admin/roads/${roadId}`)
              .then(response => response.json())
              .then(road => {
                  document.getElementById('road-id').value = road.id;
                  document.getElementById('road-name').value = road.name || '';
                  document.getElementById('road-type').value = road.road_type || '';
                  document.getElementById('road-country').value = road.country || '';
                  document.getElementById('road-capacity').value = road.hourly_capacity;

                  document.getElementById('road-modal-title').textContent = 'Edit Road';
                  roadModal.show();
              })
              .catch(error => console.error('Error loading road for edit:', error));
      }

      function saveRoad() {
          const roadId = document.getElementById('road-id').value;
          const data = {
              name: document.getElementById('road-name').value,
              road_type: document.getElementById('road-type').value,
              country: document.getElementById('road-country').value,
              hourly_capacity: parseInt(document.getElementById('road-capacity').value)
          };

          const isNewRoad = !roadId;
          const url = isNewRoad ? '/admin/roads' : `/admin/roads/${roadId}`;
          const method = isNewRoad ? 'POST' : 'PUT';

          fetchWithAuth(url, {
              method: method,
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
          })
          .then(response => {
              if (!response.ok) {
                  return response.json().then(err => { throw new Error(err.error || 'Failed to save road'); });
              }
              return response.json();
          })
          .then(result => {
              roadModal.hide();
              loadRoads();
              alert(isNewRoad ? 'Road created successfully!' : 'Road updated successfully!');
          })
          .catch(error => {
              alert(`Error: ${error.message}`);
          });
      }

      // Booking Slots data loading and actions
      function loadBookingSlots() {
    // Build URL with pagination parameters
    const url = `/admin/booking-slots?page=${currentSlotsPage}&per_page=${slotItemsPerPage}`;

    fetchWithAuth(url)
        .then(response => {
            // Extract pagination information from headers if available
            const totalCountHeader = response.headers.get('X-Total-Count');
            if (totalCountHeader) {
                totalSlotItems = parseInt(totalCountHeader);
                totalSlotPages = Math.ceil(totalSlotItems / slotItemsPerPage);
            }
            return response.json();
        })
        .then(data => {
            // Handle different response formats
            const slots = Array.isArray(data) ? data : (data.slots || []);

            // If we have pagination metadata in the response
            if (data.pagination) {
                totalSlotItems = data.pagination.total_items || totalSlotItems;
                totalSlotPages = data.pagination.total_pages || totalSlotPages;
                currentSlotsPage = data.pagination.current_page || currentSlotsPage;
            }

            // If no pagination info provided, estimate it from the data we have
            if (totalSlotItems === 0) {
                // Check if we got a full page of results
                if (slots.length >= slotItemsPerPage) {
                    // We don't know the total, but there's at least one more page
                    // Let's assume there's at least one more page
                    totalSlotItems = currentSlotsPage * slotItemsPerPage + slotItemsPerPage;
                    totalSlotPages = currentSlotsPage + 1;
                } else if (slots.length > 0) {
                    // This is likely the last page with partial results
                    totalSlotItems = (currentSlotsPage - 1) * slotItemsPerPage + slots.length;
                    totalSlotPages = currentSlotsPage;
                    // If we're on page 1, the total is just what we have
                    if (currentSlotsPage === 1) {
                        totalSlotItems = slots.length;
                        totalSlotPages = 1;
                    }
                }

                // If we're showing 20 items and got 20 items, then assume there are at least 40 total
                // (This is a fallback estimate to ensure we show pagination)
                if (currentSlotsPage === 1 && slots.length === slotItemsPerPage) {
                    totalSlotItems = slotItemsPerPage * 2; // Assume at least 2 pages
                    totalSlotPages = 2;
                }
            }

            // If we still don't have a total but have items, force some sensible defaults
            if (totalSlotPages === 0 && slots.length > 0) {
                // Force at least 2 pages if we have a full page of results
                if (slots.length >= slotItemsPerPage) {
                    totalSlotPages = 2;
                    totalSlotItems = slotItemsPerPage * 2;
                } else {
                    totalSlotPages = 1;
                    totalSlotItems = slots.length;
                }
            }

            const tableBody = document.querySelector('#slots-table tbody');
            tableBody.innerHTML = '';

            if (slots.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No booking slots found</td></tr>';
                return;
            }

            slots.forEach(slot => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${slot.road_booking_slot_id.substring(0, 8)}...</td>
                    <td>${slot.road_name || 'Unknown'}</td>
                    <td>${new Date(slot.slot_time).toLocaleString()}</td>
                    <td>${slot.capacity}</td>
                    <td>${slot.available_capacity}</td>
                    <td>${slot.created_at ? new Date(slot.created_at).toLocaleString() : 'N/A'}</td>
                    <td>
                        <button class="btn btn-sm btn-info view-slot" data-id="${slot.road_booking_slot_id}">View</button>
                        <button class="btn btn-sm btn-warning edit-slot" data-id="${slot.road_booking_slot_id}">Edit</button>
                        <button class="btn btn-sm btn-danger delete-slot" data-id="${slot.road_booking_slot_id}">Delete</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });

            // Add event listeners for the action buttons
            document.querySelectorAll('.view-slot').forEach(btn => {
                btn.addEventListener('click', () => viewBookingSlot(btn.getAttribute('data-id')));
            });

            document.querySelectorAll('.edit-slot').forEach(btn => {
                btn.addEventListener('click', () => editBookingSlot(btn.getAttribute('data-id')));
            });

            document.querySelectorAll('.delete-slot').forEach(btn => {
                btn.addEventListener('click', () => {
                    deleteItemId = btn.getAttribute('data-id');
                    deleteItemType = 'road-booking-slot';
                    deleteModal.show();
                });
            });

            // Update pagination UI
            updateSlotsPagination();
        })
        .catch(error => console.error('Error loading booking slots:', error));
}

      function loadRoadsForDropdown() {
          fetchWithAuth('/admin/roads')
              .then(response => response.json())
              .then(data => {
                  const roads = Array.isArray(data) ? data : (data.roads || []);
                  const select = document.getElementById('road-id');
                  select.innerHTML = '<option value="">Select a road</option>';

                  roads.forEach(road => {
                      const option = document.createElement('option');
                      option.value = road.id;
                      option.textContent = `${road.name || 'Unnamed'} (${road.road_type || 'Unknown'})`;
                      select.appendChild(option);
                  });
              })
              .catch(error => console.error('Error loading roads for dropdown:', error));
      }

      function viewBookingSlot(slotId) {
          fetchWithAuth(`/admin/booking-slots/${slotId}`)
              .then(response => response.json())
              .then(slot => {
                  document.getElementById('view-slot-road-name').textContent = slot.road_name || 'Unknown';
                  document.getElementById('view-slot-time').textContent = new Date(slot.slot_time).toLocaleString();
                  document.getElementById('view-slot-capacity').textContent = slot.capacity;
                  document.getElementById('view-slot-available').textContent = slot.available_capacity;
                  document.getElementById('view-slot-created').textContent =
                      slot.created_at ? new Date(slot.created_at).toLocaleString() : 'N/A';

                  viewSlotModal.show();
              })
              .catch(error => console.error('Error loading booking slot details:', error));
      }

      function editBookingSlot(slotId) {
          fetchWithAuth(`/admin/booking-slots/${slotId}`)
              .then(response => response.json())
              .then(slot => {
                  document.getElementById('slot-id').value = slot.road_booking_slot_id;
                  document.getElementById('road-id').value = slot.road_id;

                  // Format datetime for input field
                  const slotTime = new Date(slot.slot_time);
                  document.getElementById('slot-time').value = formatDateForInput(slotTime);
                  document.getElementById('capacity').value = slot.capacity;

                  document.getElementById('slot-modal-title').textContent = 'Edit Booking Slot';
                  slotModal.show();
              })
              .catch(error => console.error('Error loading booking slot for edit:', error));
      }

      function saveBookingSlot() {
          const slotId = document.getElementById('slot-id').value;
          const data = {
              road_id: document.getElementById('road-id').value,
              slot_time: document.getElementById('slot-time').value,
              capacity: parseInt(document.getElementById('capacity').value)
          };

          const isNewSlot = !slotId;
          const url = isNewSlot ? '/admin/booking-slots' : `/admin/booking-slots/${slotId}`;
          const method = isNewSlot ? 'POST' : 'PUT';

          fetchWithAuth(url, {
              method: method,
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
          })
          .then(response => {
              if (!response.ok) {
                  return response.json().then(err => { throw new Error(err.error || 'Failed to save booking slot'); });
              }
              return response.json();
          })
          .then(result => {
              slotModal.hide();
              loadBookingSlots();
              alert(isNewSlot ? 'Booking slot created successfully!' : 'Booking slot updated successfully!');
          })
          .catch(error => {
              alert(`Error: ${error.message}`);
          });
      }

      // Bookings data loading and actions
      function loadBookings() {
    // Build URL with pagination parameters
    const url = `/admin/bookings?page=${currentBookingsPage}&per_page=${bookingItemsPerPage}`;

    fetchWithAuth(url)
        .then(response => {
            // Extract pagination information from headers if available
            const totalCountHeader = response.headers.get('X-Total-Count');
            if (totalCountHeader) {
                totalBookingItems = parseInt(totalCountHeader);
                totalBookingPages = Math.ceil(totalBookingItems / bookingItemsPerPage);
            }
            return response.json();
        })
        .then(data => {
            const bookings = Array.isArray(data) ? data : (data.bookings || []);

            // If we have pagination metadata in the response
            if (data.pagination) {
                totalBookingItems = data.pagination.total_items || totalBookingItems;
                totalBookingPages = data.pagination.total_pages || totalBookingPages;
                currentBookingsPage = data.pagination.current_page || currentBookingsPage;
            }

            // If no pagination info provided, estimate it from the data we have
            if (totalBookingItems === 0) {
                // Check if we got a full page of results
                if (bookings.length >= bookingItemsPerPage) {
                    // We don't know the total, but there's at least one more page
                    // Let's assume there's at least one more page
                    totalBookingItems = currentBookingsPage * bookingItemsPerPage + bookingItemsPerPage;
                    totalBookingPages = currentBookingsPage + 1;
                } else if (bookings.length > 0) {
                    // This is likely the last page with partial results
                    totalBookingItems = (currentBookingsPage - 1) * bookingItemsPerPage + bookings.length;
                    totalBookingPages = currentBookingsPage;
                    // If we're on page 1, the total is just what we have
                    if (currentBookingsPage === 1) {
                        totalBookingItems = bookings.length;
                        totalBookingPages = 1;
                    }
                }

                // If we're showing 20 items and got 20 items, then assume there are at least 40 total
                // (This is a fallback estimate to ensure we show pagination)
                if (currentBookingsPage === 1 && bookings.length === bookingItemsPerPage) {
                    totalBookingItems = bookingItemsPerPage * 2; // Assume at least 2 pages
                    totalBookingPages = 2;
                }
            }

            // If we still don't have a total but have items, force some sensible defaults
            if (totalBookingPages === 0 && bookings.length > 0) {
                // Force at least 2 pages if we have a full page of results
                if (bookings.length >= bookingItemsPerPage) {
                    totalBookingPages = 2;
                    totalBookingItems = bookingItemsPerPage * 2;
                } else {
                    totalBookingPages = 1;
                    totalBookingItems = bookings.length;
                }
            }

            const tableBody = document.querySelector('#bookings-table tbody');
            tableBody.innerHTML = '';

            if (bookings.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="7" class="text-center">No bookings found</td></tr>';
                return;
            }

            bookings.forEach(booking => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${booking.booking_id.substring(0, 8)}...</td>
                    <td>${booking.username}</td>
                    <td>${booking.origin || 'N/A'}</td>
                    <td>${booking.destination || 'N/A'}</td>
                    <td>${booking.lines_count}</td>
                    <td>${new Date(booking.booking_timestamp).toLocaleString()}</td>
                    <td>
                        <button class="btn btn-sm btn-info view-booking" data-id="${booking.booking_id}">View</button>
                        <button class="btn btn-sm btn-danger delete-booking" data-id="${booking.booking_id}">Delete</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });

            // Add event listeners for the action buttons
            document.querySelectorAll('.view-booking').forEach(btn => {
                btn.addEventListener('click', () => viewBooking(btn.getAttribute('data-id')));
            });

            document.querySelectorAll('.delete-booking').forEach(btn => {
                btn.addEventListener('click', () => {
                    deleteItemId = btn.getAttribute('data-id');
                    deleteItemType = 'booking';
                    deleteModal.show();
                });
            });

            // Update pagination UI
            updateBookingsPagination();
        })
        .catch(error => console.error('Error loading bookings:', error));
}

      function viewBooking(bookingId) {
          fetchWithAuth(`/admin/bookings/${bookingId}`)
              .then(response => response.json())
              .then(booking => {
                  document.getElementById('view-booking-user').textContent =
                      `${booking.username} (${booking.givennames} ${booking.lastname})`;
                  document.getElementById('view-booking-origin').textContent = booking.origin || 'N/A';
                  document.getElementById('view-booking-destination').textContent = booking.destination || 'N/A';
                  document.getElementById('view-booking-time').textContent =
                      new Date(booking.booking_timestamp).toLocaleString();

                  // Populate booking lines table
                  const tableBody = document.querySelector('#booking-lines-table tbody');
                  tableBody.innerHTML = '';

                  if (booking.lines && booking.lines.length > 0) {
                      booking.lines.forEach(line => {
                          const row = document.createElement('tr');
                          row.innerHTML = `
                              <td>${line.road_name || 'Unknown'}</td>
                              <td>${new Date(line.slot_time).toLocaleString()}</td>
                              <td>${line.quantity}</td>
                          `;
                          tableBody.appendChild(row);
                      });
                  } else {
                      tableBody.innerHTML = '<tr><td colspan="3" class="text-center">No booking lines found</td></tr>';
                  }

                  viewBookingModal.show();
              })
              .catch(error => console.error('Error loading booking details:', error));
      }

      // Delete confirmation
      function confirmDelete() {
          if (!deleteItemId || !deleteItemType) {
              return;
          }

          let url;
          if (deleteItemType === 'road') {
              url = `/admin/roads/${deleteItemId}`;
          } else if (deleteItemType === 'road-booking-slot') {
              url = `/admin/road-booking-slots/${deleteItemId}`;
          } else if (deleteItemType === 'booking') {
              url = `/admin/bookings/${deleteItemId}`;
          } else {
              return;
          }

          fetchWithAuth(url, {
              method: 'DELETE'
          })
          .then(response => {
              if (!response.ok) {
                  return response.json().then(err => { throw new Error(err.error || `Failed to delete ${deleteItemType}`); });
              }
              return response.json();
          })
          .then(result => {
              deleteModal.hide();

              if (deleteItemType === 'road') {
                  loadRoads();
              } else if (deleteItemType === 'road-booking-slot') {
                  loadBookingSlots();
              } else if (deleteItemType === 'booking') {
                  loadBookings();
              }

              alert(`${deleteItemType.charAt(0).toUpperCase() + deleteItemType.slice(1)} deleted successfully!`);
          })
          .catch(error => {
              alert(`Error: ${error.message}`);
          })
          .finally(() => {
              deleteItemId = null;
              deleteItemType = null;
          });
      }

      // Helper function to initialize map
      function initMap(containerId, geojsonStr) {
          const container = document.getElementById(containerId);

          // Clear any existing map
          container.innerHTML = '';

          try {
              const geojson = typeof geojsonStr === 'string' ? JSON.parse(geojsonStr) : geojsonStr;

              // Initialize the map
              const map = L.map(containerId).setView([0, 0], 13);

              // Add OpenStreetMap tile layer
              L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              }).addTo(map);

              // Add the GeoJSON to the map
              const layer = L.geoJSON(geojson).addTo(map);

              // Fit the map to the bounds of the GeoJSON
              map.fitBounds(layer.getBounds());
          } catch (e) {
              console.error('Error initializing map:', e);
              container.innerHTML = '<p class="text-danger">Error displaying map: Invalid geometry data</p>';
          }
      }

      // Helper function to format date for datetime-local input
      function formatDateForInput(date) {
          const pad = num => num.toString().padStart(2, '0');
          return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
      }

      // Function to update pagination UI elements
      function updateSlotsPagination() {
          // Handle case where there are no items
          if (totalSlotItems === 0) {
              document.getElementById('slots-pagination-info').textContent = "Showing 0 to 0 of 0 entries";
              return;
          }

          // Update pagination info text
          const start = (currentSlotsPage - 1) * slotItemsPerPage + 1;
          const end = Math.min(currentSlotsPage * slotItemsPerPage, totalSlotItems);
          document.getElementById('slots-pagination-info').textContent =
              `Showing ${start} to ${end} of ${totalSlotItems} entries`;

          console.log(`Slots pagination updated: page ${currentSlotsPage} of ${totalSlotPages}, items per page: ${slotItemsPerPage}`); // Debug logging

          // Generate page number buttons using the improved function
          generatePaginationButtons('slots', currentSlotsPage, totalSlotPages);
      }

      // Function for roads pagination
      function updateRoadsPagination() {
          // Handle case where there are no items
          if (totalRoadItems === 0) {
              document.getElementById('roads-pagination-info').textContent = "Showing 0 to 0 of 0 entries";
              return;
          }

          // Update pagination info text
          const start = (currentRoadsPage - 1) * roadItemsPerPage + 1;
          const end = Math.min(currentRoadsPage * roadItemsPerPage, totalRoadItems);
          document.getElementById('roads-pagination-info').textContent =
              `Showing ${start} to ${end} of ${totalRoadItems} entries`;

          console.log(`Roads pagination updated: page ${currentRoadsPage} of ${totalRoadPages}, items per page: ${roadItemsPerPage}`); // Debug logging

          // Generate page number buttons using the improved function
          generatePaginationButtons('roads', currentRoadsPage, totalRoadPages);
      }

      // Function for bookings pagination
      function updateBookingsPagination() {
          // Handle case where there are no items
          if (totalBookingItems === 0) {
              document.getElementById('bookings-pagination-info').textContent = "Showing 0 to 0 of 0 entries";
              return;
          }

          // Update pagination info text
          const start = (currentBookingsPage - 1) * bookingItemsPerPage + 1;
          const end = Math.min(currentBookingsPage * bookingItemsPerPage, totalBookingItems);
          document.getElementById('bookings-pagination-info').textContent =
              `Showing ${start} to ${end} of ${totalBookingItems} entries`;

          console.log(`Bookings pagination updated: page ${currentBookingsPage} of ${totalBookingPages}, items per page: ${bookingItemsPerPage}`); // Debug logging

          // Generate page number buttons using the improved function
          generatePaginationButtons('bookings', currentBookingsPage, totalBookingPages);
      }

      // Generic function to generate pagination buttons - improved with cleaner design
      function generatePaginationButtons(section, currentPage, totalPages) {
          const paginationElement = document.getElementById(`${section}-pagination`);

          // Clear all existing page buttons
          paginationElement.innerHTML = '';

          if (totalPages <= 1) {
              // No need for pagination if there's only one page or no pages
              return;
          }

          // Add previous page button
          const prevLi = document.createElement('li');
          prevLi.classList.add('page-item');
          prevLi.classList.toggle('disabled', currentPage <= 1);

          const prevA = document.createElement('a');
          prevA.classList.add('page-link');
          prevA.href = '#';
          prevA.setAttribute('aria-label', 'Previous');
          prevA.innerHTML = '<span aria-hidden="true">&laquo;</span>';

          prevA.addEventListener('click', function(e) {
              e.preventDefault();
              if (currentPage > 1) {
                  console.log(`Going to previous ${section} page`);
                  if (section === 'roads') {
                      currentRoadsPage--;
                      loadRoads();
                  } else if (section === 'slots') {
                      currentSlotsPage--;
                      loadBookingSlots();
                  } else if (section === 'bookings') {
                      currentBookingsPage--;
                      loadBookings();
                  }
              }
          });

          prevLi.appendChild(prevA);
          paginationElement.appendChild(prevLi);

          // Determine visible page numbers
          let startPage = Math.max(1, currentPage - 2);
          let endPage = Math.min(totalPages, startPage + 4);

          // Adjust if we're showing fewer than 5 pages
          if (endPage - startPage < 4 && startPage > 1) {
              startPage = Math.max(1, endPage - 4);
          }

          // First page if not in visible range
          if (startPage > 1) {
              const firstLi = document.createElement('li');
              firstLi.classList.add('page-item');

              const firstA = document.createElement('a');
              firstA.classList.add('page-link');
              firstA.href = '#';
              firstA.textContent = '1';

              firstA.addEventListener('click', function(e) {
                  e.preventDefault();
                  console.log(`Going to first ${section} page`);
                  if (section === 'roads') {
                      currentRoadsPage = 1;
                      loadRoads();
                  } else if (section === 'slots') {
                      currentSlotsPage = 1;
                      loadBookingSlots();
                  } else if (section === 'bookings') {
                      currentBookingsPage = 1;
                      loadBookings();
                  }
              });

              firstLi.appendChild(firstA);
              paginationElement.appendChild(firstLi);

              // Add ellipsis if needed
              if (startPage > 2) {
                  const ellipsisLi = document.createElement('li');
                  ellipsisLi.classList.add('page-item', 'disabled');

                  const ellipsisA = document.createElement('a');
                  ellipsisA.classList.add('page-link');
                  ellipsisA.href = '#';
                  ellipsisA.textContent = '...';

                  ellipsisLi.appendChild(ellipsisA);
                  paginationElement.appendChild(ellipsisLi);
              }
          }

          // Visible page numbers
          for (let i = startPage; i <= endPage; i++) {
              const li = document.createElement('li');
              li.classList.add('page-item');
              if (i === currentPage) {
                  li.classList.add('active');
              }

              const a = document.createElement('a');
              a.classList.add('page-link');
              a.href = '#';
              a.textContent = i;

              a.addEventListener('click', function(e) {
                  e.preventDefault();
                  console.log(`Going to ${section} page ${i}`);
                  if (section === 'roads') {
                      currentRoadsPage = i;
                      loadRoads();
                  } else if (section === 'slots') {
                      currentSlotsPage = i;
                      loadBookingSlots();
                  } else if (section === 'bookings') {
                      currentBookingsPage = i;
                      loadBookings();
                  }
              });

              li.appendChild(a);
              paginationElement.appendChild(li);
          }

          // Last page if not in visible range
          if (endPage < totalPages) {
              // Add ellipsis if needed
              if (endPage < totalPages - 1) {
                  const ellipsisLi = document.createElement('li');
                  ellipsisLi.classList.add('page-item', 'disabled');

                  const ellipsisA = document.createElement('a');
                  ellipsisA.classList.add('page-link');
                  ellipsisA.href = '#';
                  ellipsisA.textContent = '...';

                  ellipsisLi.appendChild(ellipsisA);
                  paginationElement.appendChild(ellipsisLi);
              }

              const lastLi = document.createElement('li');
              lastLi.classList.add('page-item');

              const lastA = document.createElement('a');
              lastA.classList.add('page-link');
              lastA.href = '#';
              lastA.textContent = totalPages;

              lastA.addEventListener('click', function(e) {
                  e.preventDefault();
                  console.log(`Going to last ${section} page (${totalPages})`);
                  if (section === 'roads') {
                      currentRoadsPage = totalPages;
                      loadRoads();
                  } else if (section === 'slots') {
                      currentSlotsPage = totalPages;
                      loadBookingSlots();
                  } else if (section === 'bookings') {
                      currentBookingsPage = totalPages;
                      loadBookings();
                  }
              });

              lastLi.appendChild(lastA);
              paginationElement.appendChild(lastLi);
          }

          // Add next page button
          const nextLi = document.createElement('li');
          nextLi.classList.add('page-item');
          nextLi.classList.toggle('disabled', currentPage >= totalPages);

          const nextA = document.createElement('a');
          nextA.classList.add('page-link');
          nextA.href = '#';
          nextA.setAttribute('aria-label', 'Next');
          nextA.innerHTML = '<span aria-hidden="true">&raquo;</span>';

          nextA.addEventListener('click', function(e) {
              e.preventDefault();
              if (currentPage < totalPages) {
                  console.log(`Going to next ${section} page`);
                  if (section === 'roads') {
                      currentRoadsPage++;
                      loadRoads();
                  } else if (section === 'slots') {
                      currentSlotsPage++;
                      loadBookingSlots();
                  } else if (section === 'bookings') {
                      currentBookingsPage++;
                      loadBookings();
                  }
              }
          });

          nextLi.appendChild(nextA);
          paginationElement.appendChild(nextLi);
      }
