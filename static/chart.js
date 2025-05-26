const CATEGORY_LABELS = {
    deplacement: "déplacement",
    virement: "virement",
    nourriture_colloc: "nourriture (colloc)",
    nourriture_perso: "nourriture (gâterie)",
    jeux: "jeux"
};

function populateCategorySelect() {
    const select = document.getElementById("category");

    // Clear in case it’s re-run
    select.innerHTML = "";

    Object.entries(CATEGORY_LABELS).forEach(([value, label]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    });
}

function makeTableSortable(tableId) {
    const table = document.getElementById(tableId);
    const headers = table.querySelectorAll("thead th");
    let sortDirection = 1;

    headers.forEach((th, columnIndex) => {
        th.style.cursor = "pointer";
        th.addEventListener("click", () => {
            const tbody = table.querySelector("tbody");
            const rows = Array.from(tbody.querySelectorAll("tr"));

            rows.sort((a, b) => {
                const aText = a.children[columnIndex]?.textContent.trim();
                const bText = b.children[columnIndex]?.textContent.trim();

                const aVal = isNaN(aText) ? new Date(aText).getTime() || aText : parseFloat(aText);
                const bVal = isNaN(bText) ? new Date(bText).getTime() || bText : parseFloat(bText);

                return (aVal > bVal ? 1 : aVal < bVal ? -1 : 0) * sortDirection;
            });

            sortDirection *= -1;
            rows.forEach(row => tbody.appendChild(row));
        });
    });
}

function getCategoryColor(category) {
    const colors = {
        deplacement: "#58D68D",
        virement: "#F4D03F",
        nourriture_colloc: "#5DADE2",
        nourriture_perso: "#EB984E",
        jeux: "#EC7063",
    };
    return colors[category] || "#bbb";
}

function monthLabel(monthKey) {
    const [year, month] = monthKey.split("-");
    const monthNames = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"];
    return `${monthNames[parseInt(month) - 1]} ${year}`;
}

let chart; // global var
async function loadChartData() {
    const response = await fetch("/hist_data");
    const data = await response.json();

    // Grouping: month -> category -> amount
    const monthlyCategoryTotals = {};

    data.forEach(entry => {
        const date = new Date(entry.date);
        const monthKey = date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0");

        if (!monthlyCategoryTotals[monthKey]) {
            monthlyCategoryTotals[monthKey] = {};
        }

        const category = entry.category;
        const amount = parseFloat(entry.amount);

        if (!monthlyCategoryTotals[monthKey][category]) {
            monthlyCategoryTotals[monthKey][category] = 0;
        }

        monthlyCategoryTotals[monthKey][category] += amount;
    });

    // Extract sorted months and unique categories
    const months = Object.keys(monthlyCategoryTotals).sort();
    const categories = Array.from(
        new Set(data.map(entry => entry.category))
    );

    const datasets = categories.map(category => {
        return {
            label: CATEGORY_LABELS[category] || category,
            data: months.map(month => monthlyCategoryTotals[month][category] || 0),
            backgroundColor: getCategoryColor(category),
        };
    });

    // Draw chart
    const ctx = document.getElementById("moneyChart").getContext("2d");

    if (chart) chart.destroy();

    chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: months.map(m => monthLabel(m)), // e.g. "2024-05" → "Mai 2024"
            datasets: datasets,
        },
        options: {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    //text: 'Dépenses mensuelles par catégorie'
                },
            },
            scales: {
                x: {
                    stacked: false
                },
                y: {
                    stacked: false,
                    beginAtZero: true
                }
            }
        }
    });
}

async function loadTables() {
    const response = await fetch("/entries");
    const data = await response.json();

    // All entries
    renderTable("all-entries-table", data);

    // Filter current month
    const now = new Date();
    const currentMonthEntries = data.filter(row => {
        const date = new Date(row[1]);
        return (
            date.getFullYear() === now.getFullYear() &&
            date.getMonth() === now.getMonth()
        );
    });

    renderTable("current-month-table", currentMonthEntries, { hideActions: false });
}

function renderTable(tableId, rows, options = {}) {
    const { hideActions = false } = options;

    const table = document.getElementById(tableId);
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";

    rows.sort((a, b) => new Date(a[1]) - new Date(b[1]));

    rows.forEach(row => {
        const [id, ...fields] = row;
        const tr = document.createElement("tr");

        fields.forEach((cell, index) => {
            const td = document.createElement("td");
            if (index === 3 && cell) {
                td.textContent = CATEGORY_LABELS[cell] || cell;
                const categoryClass = "cat-" + cell.replace(/\s+/g, "-").toLowerCase();
                td.classList.add(categoryClass);
            } else {
                td.textContent = cell;
            }
            tr.appendChild(td);
        });

        if (!hideActions) {
            const actionTd = document.createElement("td");
            const buttonGroup = document.createElement("div");
            buttonGroup.classList.add("button-group");

            // delete button
            const del_button = document.createElement("button");
            del_button.textContent = "🗑";
            del_button.onclick = () => deleteEntry(id);
            buttonGroup.appendChild(del_button);

            // edit button
            const edit_button = document.createElement("button");
            edit_button.textContent = "✏️";
            edit_button.onclick = () => startEditEntry(id, fields, tr);
            buttonGroup.appendChild(edit_button);

            actionTd.appendChild(buttonGroup);
            tr.appendChild(actionTd);
        }

        tbody.appendChild(tr);
    });

    makeTableSortable(tableId);
}

async function deleteEntry(id) {
    const confirmed = confirm("Supprimer cette entrée ?");
    if (!confirmed) return;

    await fetch(`/delete/${id}`, {
        method: "DELETE",
    });

    loadTables();
    loadChartData();
}

function startEditEntry(id, fields, rowElement) {
    rowElement.innerHTML = ""; // clear current row

    const [date, amount, description, category] = fields;

    // Create editable inputs
    const dateInput = document.createElement("input");
    dateInput.type = "date";
    dateInput.value = date;

    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.step = "0.01";
    amountInput.value = amount;

    const descInput = document.createElement("input");
    descInput.type = "text";
    descInput.value = description;

    const categorySelect = document.createElement("select");
    for (const [val, label] of Object.entries(CATEGORY_LABELS)) {
        const option = document.createElement("option");
        option.value = val;
        option.textContent = label;
        if (val === category) option.selected = true;
        categorySelect.appendChild(option);
    }

    // Append inputs
    [dateInput, amountInput, descInput, categorySelect].forEach(el => {
        const td = document.createElement("td");
        td.appendChild(el);
        td.classList.add("editable-cell");
        rowElement.appendChild(td);
    });

    // Save / Cancel buttons
    const actionTd = document.createElement("td");
    const buttonGroup = document.createElement("div");
    buttonGroup.classList.add("button-group");

    const saveBtn = document.createElement("button");
    saveBtn.textContent = "💾";
    saveBtn.onclick = async () => {
        await saveEditEntry(id, {
            date: dateInput.value,
            amount: amountInput.value,
            description: descInput.value,
            category: categorySelect.value
        });
    };
    buttonGroup.appendChild(saveBtn);

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "❌";
    cancelBtn.onclick = () => loadTables(); // just reload the row
    buttonGroup.appendChild(cancelBtn);


    actionTd.appendChild(buttonGroup);
    rowElement.appendChild(actionTd);
}

async function saveEditEntry(id, updatedEntry) {
    const response = await fetch(`/update/${id}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(updatedEntry)
    });

    if (!response.ok) {
        alert("Erreur lors de la mise à jour.");
        return;
    }

    loadTables();
    loadChartData();
}

document.addEventListener("DOMContentLoaded", () => {
    populateCategorySelect();
    const form = document.getElementById("entry-form");
    // Handle form submission
    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const formData = new FormData(form);
        await fetch("/submit", {
            method: "POST",
            body: formData,
        });

        form.reset();
        loadTables();              // refresh table
        loadChartData();
    });
    // Initial page load
    loadTables();
    loadChartData();
});

// // Load chart data from backend
// async function loadChartData() {
//  const response = await fetch("/data");
//  const data = await response.json();

//  const labels = data.map(entry =>
//    new Date(entry.timestamp).toLocaleString()
//  );
//  const values = data.map(entry => entry.amount);

//  if (chart) chart.destroy();

//  chart = new Chart(ctx, {
//    type: "line",
//    data: {
//      labels: labels,
//      datasets: [{
//        label: "Expenses Entries",
//        data: values,
//        fill: false,
//        borderColor: "green",
//        tension: 0.1,
//      }],
//    },
//  });
// }
