// Booking functionality for the road map application

// Global booking-related variables
let selectedSlots = {}; // Change to object to track slots by road
let suggestedSlots = [];
let userBookings = [];
let bookingModal = null;

// Initialize booking functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap modal
    bookingModal = new bootstrap.Modal(document.getElementById('booking-modal'));

    // Add event listeners
    document.getElementById('confirm-booking-btn').addEventListener('click', confirmRouteBooking);

    // Add refresh button event listener
    document.getElementById('refresh-bookings-btn').addEventListener('click', loadUserBookings);

    // Load user's existing bookings
    loadUserBookings();

    // Configure the modal to not close when clicking inside it
    const bookingModalEl = document.getElementById('booking-modal');
    if (bookingModalEl) {
        bookingModalEl.addEventListener('click', function(event) {
            // Prevent clicks inside the modal body from closing the modal
            if (event.target.closest('.modal-body')) {
                event.stopPropagation();
            }
        });
    }
});

// Function to display the route booking modal
function showRouteBookingModal(roadIds, distance, duration) {
    if (!roadIds || roadIds.length === 0) {
        alert('No roads available to book');
        return;
    }

    // Set route information in the modal
    document.getElementById('booking-road-ids').value = JSON.stringify(roadIds);
    document.getElementById('booking-route-distance').textContent = `${(distance / 1000).toFixed(2)} km`;
    document.getElementById('booking-route-duration').textContent = duration;
    document.getElementById('booking-road-count').textContent = roadIds.length;

    // Reset selected slots
    selectedSlots = {};

    // Get suggested time slots based on route duration
    fetchAvailableTimeSlots(roadIds, duration, distance);

    // Show the modal
    bookingModal.show();
}

// Function to fetch available time slots for each road
async function fetchAvailableTimeSlots(roadIds, durationMinutes, distanceMeters) {
    try {
        // Update UI to show loading state
        const slotsContainer = document.getElementById('time-slot-selection');
        slotsContainer.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div><p>Loading available slots...</p></div>';
        document.getElementById('confirm-booking-btn').disabled = true;

        const response = await fetch('/booking/available-slots', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            },
            body: JSON.stringify({
                road_ids: roadIds,
                duration_minutes: durationMinutes,
                distance_meters: distanceMeters
            })
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const data = await response.json();

        // Process available slots for each road
        renderTimeSlotSelector(roadIds, data.available_slots, slotsContainer);

        // Enable booking button
        document.getElementById('confirm-booking-btn').disabled = false;

    } catch (error) {
        console.error('Error fetching available time slots:', error);
        document.getElementById('time-slot-selection').innerHTML = `
            <div class="alert alert-danger">
                Error loading time slots: ${error.message}
            </div>
        `;
        document.getElementById('confirm-booking-btn').disabled = true;
    }
}

// Render time slot selector for roads
function renderTimeSlotSelector(roadIds, availableSlotsData, container) {
    // Clear container
    container.innerHTML = '';

    // Create date navigation
    const dates = getUniqueDates(availableSlotsData);

    if (dates.length === 0) {
        container.innerHTML = '<div class="alert alert-warning">No available time slots found</div>';
        return;
    }

    // Create date selector
    const dateNav = document.createElement('div');
    dateNav.className = 'date-navigation mb-3';
    dateNav.innerHTML = `
        <div class="btn-group date-selector" role="group">
            ${dates.map((date, index) => `
                <button type="button" class="btn btn-outline-primary date-btn ${index === 0 ? 'active' : ''}"
                    data-date="${date.dateKey}">${date.dateDisplay}</button>
            `).join('')}
        </div>
    `;
    container.appendChild(dateNav);

    // Create container for time slots
    const slotsContainer = document.createElement('div');
    slotsContainer.className = 'time-slots-container';
    container.appendChild(slotsContainer);

    // Add event listeners to date buttons
    dateNav.querySelectorAll('.date-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            // Update active button
            dateNav.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Show slots for selected date
            const selectedDate = this.getAttribute('data-date');
            displaySlotsForDate(selectedDate, availableSlotsData, slotsContainer);
        });
    });

    // Show slots for first date by default
    if (dates.length > 0) {
        displaySlotsForDate(dates[0].dateKey, availableSlotsData, slotsContainer);
    }
}

// Helper function to get unique dates from available slots
function getUniqueDates(availableSlotsData) {
    const uniqueDates = {};

    // Loop through each road's available slots
    Object.keys(availableSlotsData).forEach(roadId => {
        const roadSlots = availableSlotsData[roadId] || [];

        roadSlots.forEach(slot => {
            const slotDate = new Date(slot.start_time);
            const dateKey = slotDate.toISOString().split('T')[0];

            if (!uniqueDates[dateKey]) {
                const displayDate = slotDate.toLocaleDateString(undefined, {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric'
                });

                uniqueDates[dateKey] = {
                    dateKey,
                    dateDisplay: displayDate,
                    date: slotDate
                };
            }
        });
    });

    // Convert to array and sort by date
    return Object.values(uniqueDates).sort((a, b) => a.date - b.date);
}

// Display slots for a specific date
function displaySlotsForDate(dateKey, availableSlotsData, container) {
    container.innerHTML = '';

    // Create a table for each road
    const roadIds = Object.keys(availableSlotsData);

    if (roadIds.length === 0) {
        container.innerHTML = '<div class="alert alert-warning">No roads with available slots</div>';
        return;
    }

    // Create scrollable container
    const scrollContainer = document.createElement('div');
    scrollContainer.className = 'slots-scroll-container';
    container.appendChild(scrollContainer);

    roadIds.forEach(roadId => {
        const roadSlots = availableSlotsData[roadId] || [];

        // Filter slots for selected date
        const dateSlots = roadSlots.filter(slot => {
            const slotDate = new Date(slot.start_time);
            const slotDateKey = slotDate.toISOString().split('T')[0];
            return slotDateKey === dateKey;
        });

        if (dateSlots.length === 0) return; // Skip roads with no slots on this date

        // Create road slots section
        const roadSection = document.createElement('div');
        roadSection.className = 'road-slots mb-4';

        roadSection.innerHTML = `
            <h5>${dateSlots[0].road_name || 'Road ' + roadId}</h5>
            <div class="slot-buttons">
                ${generateSlotButtons(roadId, dateSlots)}
            </div>
        `;

        scrollContainer.appendChild(roadSection);

        // Add event listeners to slot buttons
        roadSection.querySelectorAll('.slot-btn').forEach(btn => {
            btn.addEventListener('click', function(event) {
                // Prevent event bubbling that might close the modal
                event.preventDefault();
                event.stopPropagation();
                toggleSlotSelection(this, roadId);
                return false;
            });
        });
    });

    if (scrollContainer.children.length === 0) {
        container.innerHTML = '<div class="alert alert-info">No slots available for this date</div>';
    }
}

// Generate HTML for slot buttons
function generateSlotButtons(roadId, slots) {
    let buttonsHtml = '';

    // Group slots by hour for easier display
    const hourSlots = {};

    slots.forEach(slot => {
        const slotTime = new Date(slot.start_time);
        const hour = slotTime.getHours();

        if (!hourSlots[hour]) {
            hourSlots[hour] = {
                hour: hour,
                available: slot.available,
                start_time: slot.start_time,
                end_time: slot.end_time,
                slot_id: slot.slot_id
            };
        }
    });

    // Create buttons for each hour
    for (let hour = 0; hour < 24; hour++) {
        const slot = hourSlots[hour];
        const hourDisplay = `${hour.toString().padStart(2, '0')}:00`;

        if (slot) {
            // If slot exists and is available
            const slotData = JSON.stringify({
                start_time: slot.start_time,
                end_time: slot.end_time,
                slot_id: slot.slot_id
            });

            buttonsHtml += `
                <button class="btn slot-btn ${slot.available ? 'btn-outline-success' : 'btn-outline-danger disabled'}"
                    data-road-id="${roadId}"
                    data-slot='${slotData}'
                    ${!slot.available ? 'disabled' : ''}>
                    ${hourDisplay}
                </button>
            `;
        } else {
            // No slot data for this hour
            buttonsHtml += `
                <button class="btn btn-outline-secondary slot-btn disabled" disabled>
                    ${hourDisplay}
                </button>
            `;
        }
    }

    return buttonsHtml;
}

// Toggle slot selection
function toggleSlotSelection(button, roadId) {
    // Prevent event propagation
    event.preventDefault();
    event.stopPropagation();

    // Get slot data
    const slotData = JSON.parse(button.getAttribute('data-slot'));

    // Toggle button appearance
    button.classList.toggle('selected');
    button.classList.toggle('btn-success');
    button.classList.toggle('btn-outline-success');

    // Update selected slots tracking
    if (!selectedSlots[roadId]) {
        selectedSlots[roadId] = [];
    }

    if (button.classList.contains('selected')) {
        // Add to selected slots
        selectedSlots[roadId].push(slotData);
    } else {
        // Remove from selected slots
        selectedSlots[roadId] = selectedSlots[roadId].filter(slot =>
            slot.slot_id !== slotData.slot_id);
    }

    // Update the booking button state
    const hasSelections = Object.values(selectedSlots).some(slots => slots.length > 0);
    document.getElementById('confirm-booking-btn').disabled = !hasSelections;

    return false; // Prevent default behavior
}


// Handle route booking confirmation
async function confirmRouteBooking() {
    const roadIdsInput = document.getElementById('booking-road-ids');

    const roadIds = JSON.parse(roadIdsInput.value);

    // Validate inputs
    if (!roadIds || roadIds.length === 0) {
        alert('No roads selected for booking');
        return;
    }

    // Check if time slots were selected for all roads
    const missingRoads = roadIds.filter(id => !selectedSlots[id] || selectedSlots[id].length === 0);
    if (missingRoads.length > 0) {
        alert(`Please select time slots for all roads in your route (${missingRoads.length} missing)`);
        return;
    }

    document.getElementById('confirm-booking-btn').disabled = true;
    document.getElementById('confirm-booking-btn').textContent = 'Booking...';

    try {
        // Create bookings for all roads with their selected time slots
        const response = await fetch('/booking/create-booking', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            },
            body: JSON.stringify({
                bookings: Object.entries(selectedSlots).map(([roadId, slots]) => ({
                    road_id: roadId,
                    slots: slots
                })),
                origin: document.getElementById('route-origin')?.value || '',
                destination: document.getElementById('route-destination')?.value || ''
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Failed to create bookings');
        }

        // Close modal and show success message
        bookingModal.hide();

        // Show booking success information
        const successCount = result.success_count || 0;
        const totalCount = result.total_count || 0;

        if (successCount === totalCount) {
            alert(`Route booked successfully! Booked ${successCount} roads.`);
        } else {
            alert(`Partially successful booking: ${successCount} out of ${totalCount} roads booked. Some roads could not be booked.`);
        }

        // Reload user bookings to show the new ones
        loadUserBookings();

    } catch (error) {
        console.error('Booking error:', error);
        // alert(`Error: ${error.message}`);
        if (error.message === 'Booking failed: Road already booked') {
            alert('One or more roads in your route are already booked for the selected time slots. Please select different slots.');
            // reset the selected slots
            selectedSlots = {};
            // reload the possible slots
            fetchAvailableTimeSlots(roadIds, 0, 0);
        }
    } finally {
        document.getElementById('confirm-booking-btn').disabled = false;
        document.getElementById('confirm-booking-btn').textContent = 'Book Now';
    }
}

// Load user's existing bookings
async function loadUserBookings() {
    const container = document.getElementById('user-bookings');

    try {
        const response = await fetch('/booking/user-bookings', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            }
        });

        if (!response.ok) {
            throw new Error('Failed to fetch bookings');
        }

        const bookings = await response.json();
        userBookings = bookings;

        if (bookings.length === 0) {
            container.innerHTML = '<p class="no-bookings">You have no current bookings</p>';
            return;
        }

        let html = '<div class="booking-list">';

        // Display each booking with improved layout
        bookings.forEach(booking => {
            const startTime = new Date(booking.start_time).toLocaleString();
            const endTime = booking.end_time ? new Date(booking.end_time).toLocaleString() : 'Varies';

            html += `
                <div class="booking-item">
                    <div class="booking-header">
                        <h6>
                        <strong> Origin : </strong> ${booking.origin || 'Unknown'}

                        <strong> Destination : </strong> ${booking.destination || 'Unknown'}
                        </h6>
                    </div>
                    <div class="booking-time">
                        <span class="booking-date">${startTime}</span>
                    </div>
                    <div class="booking-details">
                        <p><strong>Roads:</strong> <span>${booking.road_count}</span></p>
                        <p><strong>Time slots:</strong> <span>${booking.booking_count}</span></p>
                    </div>
                    <button class="btn btn-sm btn-danger cancel-booking-btn" data-booking-id="${booking.booking_id}">
                        Cancel Booking
                    </button>
                </div>
            `;
        });

        html += '</div>';

        container.innerHTML = html;

        // Add event listeners for cancel buttons
        document.querySelectorAll('.cancel-booking-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const bookingId = this.getAttribute('data-booking-id');
                if (confirm(`Are you sure you want to cancel this booking?`)) {
                    cancelBooking(bookingId);
                }
            });
        });

    } catch (error) {
        console.error('Error loading bookings:', error);
        container.innerHTML = `<p class="error">Error loading bookings: ${error.message}</p>`;
    }
}

// Cancel a booking (all booking lines for all roads)
async function cancelBooking(bookingId) {
    if (!bookingId) {
        return;
    }

    try {
        // Show user that cancellation is in progress
        const cancelButtons = document.querySelectorAll(`.cancel-booking-btn[data-booking-id="${bookingId}"]`);
        cancelButtons.forEach(btn => {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Cancelling...';
        });

        const response = await fetch(`/booking/${bookingId}/cancel`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
            }
        });

        // Parse the JSON response first - so we can get detailed error information
        let result = {};
        const responseText = await response.text();

        if (responseText) {
            try {
                result = JSON.parse(responseText);
            } catch (parseError) {
                console.warn('Response was not valid JSON:', responseText.substring(0, 100));
            }
        }

        if (!response.ok) {
            // Special handling for 404 errors - booking not found
            if (response.status === 404) {
                // This is actually not an error - the booking is already gone
                console.log("Booking was already cancelled or expired.");

                // Still refresh the list to make sure UI is updated
                loadUserBookings();

                alert("This booking was already cancelled or has expired.");
                return;
            }

            // Special handling for 403 errors - not your booking
            if (response.status === 403) {
                throw new Error("You don't have permission to cancel this booking.");
            }

            // Special handling for 401 errors - authentication issues
            if (response.status === 401) {
                // Redirect to login if authentication failed
                alert("Your session has expired. Please log in again.");
                window.location.href = '/login';
                return;
            }

            // For other errors
            throw new Error(result.error || `Unable to cancel booking (Error ${response.status})`);
        }

        // Show success message
        alert(`Booking cancelled successfully. ${result.cancelled_count || 0} road slots were cancelled.`);

        // Reload the user's bookings
        loadUserBookings();
    } catch (error) {
        console.error(`Error cancelling booking:`, error);
        alert(`Error cancelling booking: ${error.message}`);

        // Re-enable cancel buttons
        const cancelButtons = document.querySelectorAll(`.cancel-booking-btn[data-booking-id="${bookingId}"]`);
        cancelButtons.forEach(btn => {
            btn.disabled = false;
            btn.textContent = 'Cancel Booking';
        });
    }
}

// Function to highlight a user's booked segment on the map
function highlightUserBooking(bookingId) {
    const booking = userBookings.find(b => b.booking_id === bookingId);
    if (!booking || !booking.geometry) return;

    // Clear previous highlights
    highlightedRoadLayer.clearLayers();

    try {
        // Parse geometry if needed
        const geometry = typeof booking.geometry === 'string'
            ? JSON.parse(booking.geometry)
            : booking.geometry;

        // Add highlighted segment to map
        const highlightedSegment = L.geoJSON(geometry, {
            style: {
                color: '#ff9900',  // Orange for booked segments
                weight: 7,
                opacity: 1
            }
        }).addTo(highlightedRoadLayer);

        // Zoom to the segment
        map.fitBounds(highlightedSegment.getBounds(), {
            padding: [50, 50],
            maxZoom: 18
        });
    } catch (error) {
        console.error('Error highlighting booked segment:', error);
    }
}
