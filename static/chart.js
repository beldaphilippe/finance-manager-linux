const CATEGORY_CONFIG = {
    deplacement: {
        label: "déplacement",
        color: "#A3E4D7",
    },
    virement: {
        label: "virement",
        color: "#F9E79F",
    },
    nourriture_colloc: {
        label: "nourriture (colloc)",
        color: "#AED6F1",
    },
    nourriture_perso: {
        label: "nourriture (gâterie)",
        color: "#FAD7A0",
    },
    divers: {
        label: "divers",
        color: "#D7DBDD",
    },
    jeux: {
        label: "jeux",
        color: "#F5B7B1",
    },
    abonnement: {
        label: "abonnement",
        color: "#D2B4DE",
    },
    cadeaux: {
        label: "cadeaux",
        color: "#F5CBA7",
    }
};

function generateCategoryCSS() {
    return Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => {
        return `.cat-${key} {
      background-color: ${cfg.color};
      color: #333;
      font-weight: bold;
      text-align: center;
    }`;
    }).join("\n");
}

function populateCategorySelect() {
    const select = document.getElementById("category");

    // Clear in case it’s re-run
    select.innerHTML = "";

    Object.entries(CATEGORY_CONFIG).forEach(([value, config]) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = config.label;
        select.appendChild(option);
    });
}

function getCategoryColor(category) {
    return CATEGORY_CONFIG[category]?.color || "#bbb";
}

function makeTableSortable(tableId) {
    const table = document.getElementById(tableId);
    const headers = table.querySelectorAll("thead th");
    let sortDirection = 1;

    headers.forEach((th, columnIndex) => {
        if (columnIndex != 4) { // Actions not sortable
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
        };
    });
}

function monthLabel(monthKey) {
    const [year, month] = monthKey.split("-");
    const monthNames = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"];
    return `${monthNames[parseInt(month) - 1]} ${year}`;
}


function renderTable(tableId, rows, options = {}) {
    const { hideActions = false } = options;

    const table = document.getElementById(tableId);
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";

    rows.sort((a, b) => new Date(b[1]) - new Date(a[1]));

    rows.forEach(row => {
        const [id, ...fields] = row;
        const tr = document.createElement("tr");

        fields.forEach((cell, index) => {
            const td = document.createElement("td");
            if (index === 0) {  // Date
                td.textContent = new Date(cell).toLocaleDateString("fr-FR");
            } else if (index === 3 && cell) { // Categories
                td.textContent = CATEGORY_CONFIG[cell].label || cell;
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

function renderBalanceTable(tableId, rows) {
    const table = document.getElementById(tableId);
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";

    rows.sort((a, b) => new Date(b[1]) - new Date(a[1]));

    rows.forEach(row => {
        const [...fields] = row;
        const tr = document.createElement("tr");

        fields.forEach((cell, index) => {
            const td = document.createElement("td");
            if (index === 0) {  // Date
                td.textContent = new Date(cell).toLocaleDateString("fr-FR", {
                    year: "numeric",
                    month: "long"
                });
            } else {
                td.textContent = cell;
            }
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });

    makeTableSortable(tableId);
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
            label: CATEGORY_CONFIG[category].label || category,
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

async function loadBalanceTable() {
    const response = await fetch("/entries");
    const data = await response.json();

    // Group and sum by month (format: "YYYY-MM")
    const monthlyTotals = {};

    data.forEach(row => {
        const date = new Date(row[1]);
        const amount = parseFloat(row[2]);
        const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
        
        if (!monthlyTotals[monthKey]) {
            monthlyTotals[monthKey] = 0;
        }
        monthlyTotals[monthKey] += amount;
    });

    // Transform to array of [monthKey, amount] rows
    const rows = Object.entries(monthlyTotals).map(([month, total]) => {
        return [month, total.toFixed(2)];
    });

    renderBalanceTable("monthly-balance-table", rows);
}

async function loadEntryTables() {
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

async function deleteEntry(id) {
    const confirmed = confirm("Supprimer cette entrée ?");
    if (!confirmed) return;

    await fetch(`/delete/${id}`, {
        method: "DELETE",
    });

    loadEntryTables();
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
    for (const [val, config] of Object.entries(CATEGORY_CONFIG)) {
        const option = document.createElement("option");
        option.value = val;
        option.textContent = config.label;
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
    cancelBtn.onclick = () => loadEntryTables(); // just reload the row
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

    loadEntryTables();
    loadChartData();
}


let lastEnteredDate = new Date().toISOString().substring(0, 10); // default today
let warnOnExit = true;

document.addEventListener("DOMContentLoaded", () => {
    // Inject dynamic CSS for categories
    const style = document.createElement("style");
    style.innerHTML = generateCategoryCSS();
    document.head.appendChild(style);

    populateCategorySelect(); // fills a dropdown list

    document.getElementById("action-form").addEventListener("submit", async (e) => {
        e.preventDefault(); // prevent page reload
        
        warnOnExit = false;
        
        const button = e.submitter;  // the button that was clicked
        
        if (button.id === "save") {
            // Call /save
            
            await fetch("/save");
            alert("Sauvegarde effectuée.");
        } else if (button.id === "logout") {
            // Redirect to /logout
            window.location.href = "/logout";
        } else if (button.id === "local_copy") {
            // Download local backup
            window.location.href = "/local_copy";
            alert("Copie locale enregistrée.");
        }
        
        warnOnExit = true;
    });
    
    const entry_form = document.getElementById("entry-form");
    const dateInput = document.getElementById("date");

    // Set default value on page load
    dateInput.value = lastEnteredDate;

    entry_form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const formData = new FormData(entry_form);

        // Save current date value before reset
        lastEnteredDate = dateInput.value;

        
        await fetch("/submit", {
            method: "POST",
            body: formData,
        });

        entry_form.reset();
        dateInput.value = lastEnteredDate; // re-apply last date

        loadEntryTables();
        loadBalanceTable();
        loadChartData();
    });
    

    // Initial table/chart load
    loadEntryTables();
    loadBalanceTable();
    loadChartData();
});


window.addEventListener("beforeunload", function (e) {
    if (!warnOnExit) return;
    e.preventDefault();
});

// // Disable warning on manual save
// document.querySelectorAll('form[action$="/logout"]').forEach(form => {
//     form.addEventListener('submit', () => {
//         warnOnExit = false;
//     });
// });
